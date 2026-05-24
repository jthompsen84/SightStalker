"""
sightstalker.artifacts.paths — artifact filesystem containment authority.

``ArtifactPaths`` is the sole authority for translating relative artifact paths
into safe absolute paths under a trusted data directory. It enforces, at
runtime:

- relative-only inputs (no absolute, empty, ``.``, or ``..`` components);
- NUL-byte rejection;
- resolved containment under the data root;
- rejection of *any* symlink in the parent chain or at the target, even if it
  resolves back inside the data directory (ARTIFACTS-1 reject-all policy);
- non-directory parent-component rejection.

Public exceptions never include the absolute data-dir path.
"""

from __future__ import annotations

from pathlib import Path

from sightstalker.artifacts.errors import ArtifactPathError

_DIR_MODE = 0o700


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except (OSError, NotImplementedError):
        pass


class ArtifactPaths:
    """Resolved-root containment authority for one artifact data directory."""

    data_dir: Path

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        # Resolve once; resolve() is non-strict and works before creation.
        self._root = self.data_dir.resolve()

    # ------------------------------------------------------------------
    # Root management
    # ------------------------------------------------------------------

    def ensure_data_dir(self) -> Path:
        """Ensure the data root exists as a directory; create it if missing.

        Rejects an existing non-directory root. Applies best-effort ``0o700``.
        """
        root = self._root
        if root.exists():
            if not root.is_dir():
                raise ArtifactPathError("data directory path is not a directory")
        else:
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise ArtifactPathError("data directory could not be created") from None
        _chmod_best_effort(root, _DIR_MODE)
        return root

    # ------------------------------------------------------------------
    # Relative-path validation
    # ------------------------------------------------------------------

    def assert_safe_relative_path(self, relative_path: Path) -> Path:
        """Validate the lexical shape of a relative artifact path.

        Returns the cleaned ``Path`` (unchanged components) on success. Does not
        touch the filesystem; symlink/containment checks happen on resolve.
        """
        rel = Path(relative_path)
        raw = str(rel)
        if "\x00" in raw:
            raise ArtifactPathError("artifact path contains a NUL byte")
        if rel.is_absolute():
            raise ArtifactPathError("artifact path must be relative")
        if raw == "" or raw == ".":
            raise ArtifactPathError("artifact path must not be empty")
        parts = rel.parts
        if not parts:
            raise ArtifactPathError("artifact path must not be empty")
        for part in parts:
            if part == "..":
                raise ArtifactPathError("artifact path must not contain traversal")
            if part == "." or part == "":
                raise ArtifactPathError("artifact path component is invalid")
        return rel

    # ------------------------------------------------------------------
    # Symlink scanning
    # ------------------------------------------------------------------

    def scan_no_symlinks(self, relative: Path, *, include_target: bool) -> None:
        """Reject any symlink along ``relative`` below the resolved root.

        Parent components are always checked. The final component is checked
        when ``include_target`` is True (used for reads of existing targets and
        for write-target pre-checks).
        """
        current = self._root
        parts = relative.parts
        last_index = len(parts) - 1
        for index, part in enumerate(parts):
            current = current / part
            is_target = index == last_index
            if current.is_symlink():
                raise ArtifactPathError("artifact path component is a symlink")
            if not is_target and current.exists() and not current.is_dir():
                raise ArtifactPathError("artifact parent component is not a directory")

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve_relative_path(
        self, relative_path: Path, *, require_within_target_symlink_check: bool = True
    ) -> Path:
        """Resolve a relative artifact path to a safe absolute path.

        Validates lexical shape, rejects symlinks in the parent chain and at the
        target, and confirms the resolved path stays within the data root.
        """
        rel = self.assert_safe_relative_path(relative_path)
        self.scan_no_symlinks(rel, include_target=require_within_target_symlink_check)
        candidate = self._root / rel
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._root):
            raise ArtifactPathError("artifact path escapes the data directory")
        return resolved

    def relative_to_data_dir(self, path: Path) -> Path:
        """Return ``path`` expressed relative to the data directory.

        Rejects paths that resolve outside the data directory or that traverse a
        symlinked component inside it.
        """
        target = Path(path)
        if not target.is_absolute():
            target = self._root / target
        resolved = target.resolve()
        if not resolved.is_relative_to(self._root):
            raise ArtifactPathError("path is outside the data directory")
        try:
            lexical_rel = target.relative_to(self._root)
        except ValueError:
            raise ArtifactPathError("path is outside the data directory") from None
        self.scan_no_symlinks(lexical_rel, include_target=False)
        return resolved.relative_to(self._root)

    # ------------------------------------------------------------------
    # Parent directory creation
    # ------------------------------------------------------------------

    def ensure_parent_dir(self, relative_path: Path) -> Path:
        """Create the parent directory for a relative artifact path safely.

        Returns the absolute parent directory. The parent must not be (or pass
        through) a symlink, and must remain within the data root.
        """
        rel = self.assert_safe_relative_path(relative_path)
        self.ensure_data_dir()
        parent_rel = rel.parent
        # Walk and create each component, rejecting symlinks as we go.
        current = self._root
        for part in parent_rel.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactPathError("artifact parent component is a symlink")
            if current.exists():
                if not current.is_dir():
                    raise ArtifactPathError(
                        "artifact parent component is not a directory"
                    )
            else:
                try:
                    current.mkdir(exist_ok=True)
                except OSError:
                    raise ArtifactPathError(
                        "artifact parent directory could not be created"
                    ) from None
                _chmod_best_effort(current, _DIR_MODE)
        resolved = current.resolve()
        if not resolved.is_relative_to(self._root):
            raise ArtifactPathError("artifact parent escapes the data directory")
        return resolved
