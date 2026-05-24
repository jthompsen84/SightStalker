"""
sightstalker.artifacts.manager — reusable artifact manager.

``ArtifactManager`` writes, reads, verifies, and references artifact files under
a trusted data directory. It generalizes the hardened storage-state behavior
from SESSION-STATE-1:

- runtime validation of artifact type / id / ref / relative path;
- resolved containment + reject-all-symlink path safety;
- no-overwrite, race-hardened exclusive creation (``O_CREAT|O_EXCL`` and, where
  available, ``O_NOFOLLOW``), regular-file fd check, fsync of file and parent;
- SHA-256 + size computed from the bytes actually on disk;
- read-returns-the-verified-buffer semantics (no verify-then-reread TOCTOU);
- MIME/type provenance on the returned ``ArtifactRef``.

This layer adds no diagnostics, browser, SQL, CLI, or web behavior, and never
imports ``sightstalker.sessions``.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from pydantic import TypeAdapter

from sightstalker.artifacts.errors import (
    ArtifactError,
    ArtifactExistsError,
    ArtifactIntegrityError,
    ArtifactPathError,
    UnsupportedArtifactTypeError,
)
from sightstalker.artifacts.hashing import compute_sha256
from sightstalker.artifacts.mime import infer_mime_type
from sightstalker.artifacts.paths import ArtifactPaths
from sightstalker.ids import new_artifact_id
from sightstalker.models import (
    ArtifactId,
    ArtifactRef,
    ArtifactType,
    JsonValue,
)

_FILE_MODE = 0o600

_ARTIFACT_ID_ADAPTER: TypeAdapter[ArtifactId] = TypeAdapter(ArtifactId)
_ARTIFACT_TYPE_ADAPTER: TypeAdapter[ArtifactType] = TypeAdapter(ArtifactType)
_ARTIFACT_REF_ADAPTER: TypeAdapter[ArtifactRef] = TypeAdapter(ArtifactRef)

# O_NOFOLLOW is POSIX; absent on some platforms (e.g. Windows).
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)


class ArtifactManager:
    """Writes/reads/verifies artifact files under a trusted data directory."""

    def __init__(self, paths: ArtifactPaths) -> None:
        self._paths = paths

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_type(artifact_type: ArtifactType) -> ArtifactType:
        try:
            return _ARTIFACT_TYPE_ADAPTER.validate_python(artifact_type)
        except Exception:
            raise UnsupportedArtifactTypeError("unknown artifact type") from None

    @staticmethod
    def _validate_id(artifact_id: ArtifactId) -> ArtifactId:
        try:
            return _ARTIFACT_ID_ADAPTER.validate_python(artifact_id)
        except Exception:
            raise ArtifactPathError("artifact id is malformed") from None

    def _validate_ref(self, ref: ArtifactRef) -> ArtifactRef:
        """Re-validate a ref's fields, defeating ``model_construct`` bypasses."""
        try:
            validated = _ARTIFACT_REF_ADAPTER.validate_python(
                ref.model_dump(mode="python")
            )
        except Exception:
            raise ArtifactPathError("artifact reference is malformed") from None
        # relative_path must be relative regardless of model state.
        if validated.relative_path.is_absolute():
            raise ArtifactPathError("artifact reference path must be relative")
        return validated

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def resolve(self, ref: ArtifactRef) -> Path:
        """Resolve ``ref`` to a safe absolute path (no read performed)."""
        validated = self._validate_ref(ref)
        return self._paths.resolve_relative_path(validated.relative_path)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def write_bytes(
        self,
        *,
        relative_path: Path,
        artifact_type: ArtifactType,
        data: bytes,
        artifact_id: ArtifactId | None = None,
        mime_type: str | None = None,
    ) -> ArtifactRef:
        """Write ``data`` to ``relative_path`` with no-overwrite semantics."""
        atype = self._validate_type(artifact_type)
        rel = self._paths.assert_safe_relative_path(relative_path)
        aid = self._validate_id(artifact_id) if artifact_id is not None else None

        # Reject a symlinked parent/target before creating anything.
        self._paths.scan_no_symlinks(rel, include_target=True)
        parent = self._paths.ensure_parent_dir(rel)
        target = parent / rel.name

        self._exclusive_write(target, data)

        # Re-resolve and confirm containment after the write.
        resolved = target.resolve()
        relative = self._paths.relative_to_data_dir(resolved)

        digest = compute_sha256(data)
        size = len(data)
        resolved_mime = infer_mime_type(atype, rel, explicit=mime_type)
        ref_id = aid if aid is not None else new_artifact_id(atype.split("_")[0])

        return ArtifactRef(
            artifact_id=ref_id,
            artifact_type=atype,
            relative_path=relative,
            sha256=digest,
            size_bytes=size,
            mime_type=resolved_mime,
            hash_algorithm="sha256",
        )

    def write_text(
        self,
        *,
        relative_path: Path,
        artifact_type: ArtifactType,
        text: str,
        encoding: str = "utf-8",
        artifact_id: ArtifactId | None = None,
        mime_type: str | None = None,
    ) -> ArtifactRef:
        """Encode ``text`` and write it with no-overwrite semantics."""
        try:
            data = text.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            raise ArtifactError("artifact text could not be encoded") from None
        return self.write_bytes(
            relative_path=relative_path,
            artifact_type=artifact_type,
            data=data,
            artifact_id=artifact_id,
            mime_type=mime_type,
        )

    def write_json(
        self,
        *,
        relative_path: Path,
        artifact_type: ArtifactType,
        payload: JsonValue,
        artifact_id: ArtifactId | None = None,
        mime_type: str | None = None,
    ) -> ArtifactRef:
        """Serialize ``payload`` canonically and write with no-overwrite.

        Canonical form matches the SESSION-STATE-1 byte format: UTF-8,
        ``sort_keys``, compact separators, no trailing newline, ``allow_nan``
        disabled.
        """
        try:
            data = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except ValueError:
            # allow_nan=False raises ValueError on NaN/Infinity.
            raise ArtifactError("artifact JSON payload is not serializable") from None
        return self.write_bytes(
            relative_path=relative_path,
            artifact_type=artifact_type,
            data=data,
            artifact_id=artifact_id,
            mime_type=mime_type,
        )

    @staticmethod
    def _exclusive_write(target: Path, payload: bytes) -> None:
        """Create ``target`` exclusively and write ``payload`` durably.

        Uses ``O_CREAT|O_EXCL|O_WRONLY`` (+``O_NOFOLLOW`` where available). An
        existing target raises ``ArtifactExistsError``. The fd is confirmed to
        be a regular file, the data is fsynced, and the parent directory is
        fsynced best-effort. On failure after the exclusive create, the
        incomplete file is unlinked (exclusive-create proves ownership).
        """
        if target.is_symlink():
            raise ArtifactPathError("artifact target is a symlink")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_NOFOLLOW | _O_BINARY
        try:
            fd = os.open(target, flags, _FILE_MODE)
        except FileExistsError:
            raise ArtifactExistsError("artifact file already exists") from None
        except OSError:
            # E.g. ELOOP from O_NOFOLLOW hitting a symlink, or permission error.
            raise ArtifactPathError("artifact file could not be created") from None

        owned = True
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ArtifactPathError("artifact target is not a regular file")
            with os.fdopen(fd, "wb") as handle:
                owned = False  # fdopen now owns the descriptor.
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            if owned:
                try:
                    os.close(fd)
                except OSError:
                    pass
            # Exclusive create proved ownership; clean up the partial file.
            try:
                target.unlink()
            except OSError:
                pass
            raise

        # Best-effort: enforce 0o600 (O_CREAT honours umask) and fsync parent.
        try:
            os.chmod(target, _FILE_MODE)
        except (OSError, NotImplementedError):
            pass
        _fsync_dir(target.parent)

    # ------------------------------------------------------------------
    # Reads / verification
    # ------------------------------------------------------------------

    def read_bytes(self, ref: ArtifactRef) -> bytes:
        """Read, verify, and return the artifact bytes.

        Reads the file exactly once into a buffer, computes size and SHA-256
        over that buffer, compares to ``ref``, and returns the same buffer.
        """
        validated = self._validate_ref(ref)
        absolute = self._paths.resolve_relative_path(validated.relative_path)
        if absolute.is_symlink():
            raise ArtifactPathError("artifact target is a symlink")
        try:
            fd = os.open(absolute, os.O_RDONLY | _O_NOFOLLOW | _O_BINARY)
        except OSError:
            raise ArtifactIntegrityError(
                "referenced artifact file is missing or unreadable"
            ) from None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ArtifactPathError("artifact target is not a regular file")
            with os.fdopen(fd, "rb") as handle:
                raw = handle.read()
        except ArtifactError:
            raise
        except OSError:
            raise ArtifactIntegrityError(
                "referenced artifact file is unreadable"
            ) from None

        if len(raw) != validated.size_bytes:
            raise ArtifactIntegrityError("artifact size mismatch")
        if compute_sha256(raw) != validated.sha256:
            raise ArtifactIntegrityError("artifact hash mismatch")
        return raw

    def read_text(self, ref: ArtifactRef, *, encoding: str = "utf-8") -> str:
        """Read+verify the artifact and decode the verified buffer."""
        raw = self.read_bytes(ref)
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            raise ArtifactIntegrityError("artifact text could not be decoded") from None

    def read_json(self, ref: ArtifactRef) -> JsonValue:
        """Read+verify the artifact and parse the verified buffer as JSON."""
        raw = self.read_bytes(ref)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ArtifactIntegrityError("artifact JSON is invalid") from None

    def verify(self, ref: ArtifactRef) -> None:
        """Verify the artifact's size and hash; raise on any mismatch."""
        # read_bytes performs the full verification; discard the buffer.
        self.read_bytes(ref)


def _fsync_dir(path: Path) -> None:
    """Best-effort fsync of a directory for write durability."""
    try:
        dir_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        try:
            os.close(dir_fd)
        except OSError:
            pass
