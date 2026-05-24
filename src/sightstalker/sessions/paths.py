"""
sightstalker.sessions.paths — filesystem layout authority and path safety.

``SessionPaths`` is the *sole* authority for SightStalker's on-disk layout. It
builds profile/run/state paths from validated identifiers and enforces runtime
containment so that no externally supplied identifier or relative path can
escape the configured data directory.

On-disk layout:

    <data_dir>/
    └── profiles/
        └── <profile_id>/
            ├── .sightstalker-profile.lock
            └── runs/
                └── <run_id>/
                    ├── storage_state.initial.json
                    └── storage_state.final.json

Note: this PR does NOT create or use a browser ``user_data_dir``. ``profile_dir``
here is a SightStalker-owned state container, not a persistent browser profile.
"""

from __future__ import annotations

from pathlib import Path

from sightstalker.models import ProfileId, RunId
from sightstalker.sessions.ids import validate_profile_id, validate_run_id

_PROFILES_DIR_NAME = "profiles"
_RUNS_DIR_NAME = "runs"
_PROFILE_LOCK_NAME = ".sightstalker-profile.lock"
_STORAGE_STATE_INITIAL_NAME = "storage_state.initial.json"
_STORAGE_STATE_FINAL_NAME = "storage_state.final.json"

_DIR_MODE = 0o700


def _chmod_best_effort(path: Path, mode: int) -> None:
    """Apply ``mode`` to ``path`` where the platform supports it."""
    try:
        path.chmod(mode)
    except (OSError, NotImplementedError):
        # POSIX permissions may be unsupported (e.g. some Windows setups).
        pass


class SessionPaths:
    """Resolved-root filesystem authority for one SightStalker data directory."""

    data_dir: Path

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        # Resolve once. ``resolve()`` is non-strict and works even when the
        # directory does not exist yet. All builders work from the resolved
        # root so that containment checks and symlink scans are consistent.
        self._root = self.data_dir.resolve()

    # ------------------------------------------------------------------
    # Path builders (each validates externally supplied identifiers)
    # ------------------------------------------------------------------

    def profile_dir(self, profile_id: ProfileId) -> Path:
        validated = validate_profile_id(profile_id)
        return self._root / _PROFILES_DIR_NAME / validated

    def profile_lock_path(self, profile_id: ProfileId) -> Path:
        return self.profile_dir(profile_id) / _PROFILE_LOCK_NAME

    def runs_dir(self, profile_id: ProfileId) -> Path:
        return self.profile_dir(profile_id) / _RUNS_DIR_NAME

    def run_dir(self, profile_id: ProfileId, run_id: RunId) -> Path:
        validated_run = validate_run_id(run_id)
        return self.runs_dir(profile_id) / validated_run

    def storage_state_initial_path(
        self, profile_id: ProfileId, run_id: RunId
    ) -> Path:
        return self.run_dir(profile_id, run_id) / _STORAGE_STATE_INITIAL_NAME

    def storage_state_final_path(
        self, profile_id: ProfileId, run_id: RunId
    ) -> Path:
        return self.run_dir(profile_id, run_id) / _STORAGE_STATE_FINAL_NAME

    # ------------------------------------------------------------------
    # Containment helpers
    # ------------------------------------------------------------------

    def _scan_symlinks(self, relative: Path) -> None:
        """
        Reject any symlinked component below the resolved data root.

        ``relative`` must be expressed relative to ``self._root``. The resolved
        root itself is symlink-free, so any symlink encountered while walking
        ``relative`` lives inside the managed tree and is rejected.
        """
        current = self._root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlinked path component is not allowed")

    def relative_to_data_dir(self, path: Path) -> Path:
        """
        Return ``path`` expressed relative to the data directory.

        Rejects paths that resolve outside the data directory and paths that
        traverse a symlinked component inside the data directory.
        """
        target = Path(path)
        if not target.is_absolute():
            target = self._root / target
        resolved = target.resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("path is outside the data directory")
        try:
            lexical_rel = target.relative_to(self._root)
        except ValueError:
            # Path was not lexically under the resolved root.
            raise ValueError("path is outside the data directory") from None
        self._scan_symlinks(lexical_rel)
        return resolved.relative_to(self._root)

    def resolve_relative_path(self, relative_path: Path) -> Path:
        """
        Resolve a stored relative path back to a safe absolute path.

        Rejects absolute paths, ``..`` traversal, symlinked components, and any
        candidate that resolves outside the data directory.
        """
        rel = Path(relative_path)
        if rel.is_absolute():
            raise ValueError("relative_path must not be absolute")
        if any(part == ".." for part in rel.parts):
            raise ValueError("relative_path must not contain traversal")
        candidate = self._root / rel
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("relative_path escapes the data directory")
        self._scan_symlinks(rel)
        return resolved

    # ------------------------------------------------------------------
    # Layout creation (best-effort permissions)
    # ------------------------------------------------------------------

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(path, _DIR_MODE)

    def ensure_profile_layout(self, profile_id: ProfileId) -> None:
        validated = validate_profile_id(profile_id)
        self._ensure_dir(self._root)
        self._ensure_dir(self.profile_dir(validated))
        self._ensure_dir(self.runs_dir(validated))

    def ensure_run_layout(self, profile_id: ProfileId, run_id: RunId) -> None:
        validated_profile = validate_profile_id(profile_id)
        validated_run = validate_run_id(run_id)
        self._ensure_dir(self.run_dir(validated_profile, validated_run))
