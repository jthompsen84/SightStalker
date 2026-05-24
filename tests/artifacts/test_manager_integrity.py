"""ArtifactManager integrity/verification tests (spec 13.6, 19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sightstalker.artifacts import (
    ArtifactIntegrityError,
    ArtifactManager,
    ArtifactPathError,
    ArtifactPaths,
)
from sightstalker.models import ArtifactRef


def _mgr(tmp_path: Path) -> ArtifactManager:
    paths = ArtifactPaths(tmp_path)
    paths.ensure_data_dir()
    return ArtifactManager(paths)


def _supports_symlinks(tmp_path: Path) -> bool:
    try:
        t = tmp_path / "_t"
        t.mkdir()
        link = tmp_path / "_l"
        link.symlink_to(t)
        link.unlink()
        t.rmdir()
        return True
    except (OSError, NotImplementedError):
        return False


def _write(mgr: ArtifactManager, tmp_path: Path) -> ArtifactRef:
    return mgr.write_bytes(
        relative_path=Path("r/a.bin"),
        artifact_type="diagnostic_bundle",
        data=b"the original payload",
    )


def test_verify_ok(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    mgr.verify(ref)  # no raise


def test_tamper_detected(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    target = tmp_path.resolve() / ref.relative_path
    target.unlink()
    target.write_bytes(b"the tampered payload")  # same length, different bytes
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_bytes(ref)


def test_truncation_detected(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    target = tmp_path.resolve() / ref.relative_path
    target.unlink()
    target.write_bytes(b"short")
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_bytes(ref)


def test_append_detected(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    target = tmp_path.resolve() / ref.relative_path
    with open(target, "ab") as fh:
        fh.write(b"extra")
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_bytes(ref)


def test_hash_mismatch_detected(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    bad = ref.model_copy(update={"sha256": "b" * 64})
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_bytes(bad)


def test_size_mismatch_detected(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    bad = ref.model_copy(update={"size_bytes": ref.size_bytes + 1})
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_bytes(bad)


def test_missing_file_detected(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = _write(mgr, tmp_path)
    (tmp_path.resolve() / ref.relative_path).unlink()
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_bytes(ref)


def test_read_rejects_absolute_ref(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = ArtifactRef(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="diagnostic_bundle",
        relative_path=Path("/etc/passwd"),
        sha256="a" * 64,
        size_bytes=1,
        mime_type="application/zip",
    )
    with pytest.raises(ArtifactPathError):
        mgr.read_bytes(ref)


def test_read_rejects_traversal_ref(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = ArtifactRef(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="diagnostic_bundle",
        relative_path=Path("..") / ".." / "escape.bin",
        sha256="a" * 64,
        size_bytes=1,
        mime_type="application/zip",
    )
    with pytest.raises(ArtifactPathError):
        mgr.read_bytes(ref)


def test_read_rejects_symlinked_target(tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("no symlink support")
    from sightstalker.artifacts.hashing import compute_sha256

    root = tmp_path / "data"
    paths = ArtifactPaths(root)
    paths.ensure_data_dir()
    mgr = ArtifactManager(paths)
    (root / "r").mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "secret.bin"
    payload = b"secret"
    outside.write_bytes(payload)
    link = root / "r" / "ln.bin"
    link.symlink_to(outside)
    ref = ArtifactRef(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="diagnostic_bundle",
        relative_path=Path("r/ln.bin"),
        sha256=compute_sha256(payload),
        size_bytes=len(payload),
        mime_type="application/zip",
    )
    with pytest.raises(ArtifactPathError):
        mgr.read_bytes(ref)


def test_read_rejects_malformed_construct_before_read(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    bad = ArtifactRef.model_construct(
        artifact_id="bad id",
        artifact_type="diagnostic_bundle",
        relative_path=Path("r/a.bin"),
        sha256="not-a-real-hash",
        size_bytes=5,
        mime_type="application/zip",
        hash_algorithm="sha256",
    )
    with pytest.raises(ArtifactPathError):
        mgr.read_bytes(bad)


def test_read_returns_verified_buffer_identity(tmp_path: Path) -> None:
    # read_bytes must verify and return the SAME bytes it hashed.
    mgr = _mgr(tmp_path)
    data = b"deterministic content for buffer identity"
    ref = mgr.write_bytes(
        relative_path=Path("r/b.bin"),
        artifact_type="diagnostic_bundle",
        data=data,
    )
    out = mgr.read_bytes(ref)
    assert out == data
