"""
sightstalker.diagnostics.paths — diagnostic artifact path policy.

``DiagnosticPathPolicy`` is the single authority for diagnostic relative-path
construction and suffix validation. It returns relative POSIX paths embedding
the same artifact ID that will appear in the resulting ``ArtifactRef``.

Layouts:

    diagnostics/runs/<run_id>/<artifact_id>.<suffix>
    diagnostics/unscoped/<artifact_id>.<suffix>
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from sightstalker.diagnostics.errors import DiagnosticCaptureError
from sightstalker.models import ArtifactId, RunId

_KIND_SUFFIX = {
    "screenshot": ".png",
    "trace": ".zip",
    "console": ".jsonl",
}


class DiagnosticPathPolicy:
    """Builds and validates relative paths for diagnostic artifacts."""

    @staticmethod
    def validate_suffix(kind: str, suffix: str) -> str:
        """Validate a filename suffix for ``kind`` and return it unchanged."""
        expected = _KIND_SUFFIX.get(kind)
        if expected is None:
            raise DiagnosticCaptureError("unknown diagnostic kind")
        if suffix == "" or suffix in (".", ".."):
            raise DiagnosticCaptureError("diagnostic suffix must not be empty")
        if "/" in suffix or "\\" in suffix:
            raise DiagnosticCaptureError(
                "diagnostic suffix must not contain path separators"
            )
        if "\x00" in suffix:
            raise DiagnosticCaptureError("diagnostic suffix is invalid")
        if ".." in suffix:
            raise DiagnosticCaptureError("diagnostic suffix must not contain traversal")
        if not suffix.endswith(expected):
            raise DiagnosticCaptureError(
                f"{kind} suffix must end with {expected}"
            )
        return suffix

    def artifact_relative_path(
        self,
        *,
        artifact_id: ArtifactId,
        kind: str,
        suffix: str,
        run_id: RunId | None = None,
    ) -> Path:
        """Return the relative diagnostic path embedding ``artifact_id``."""
        validated_suffix = self.validate_suffix(kind, suffix)
        name = f"{artifact_id}.{validated_suffix}"
        if run_id is not None:
            rel = PurePosixPath("diagnostics") / "runs" / run_id / name
        else:
            rel = PurePosixPath("diagnostics") / "unscoped" / name
        path = Path(rel)
        if path.is_absolute():
            raise DiagnosticCaptureError("diagnostic path must be relative")
        if any(part == ".." for part in path.parts):
            raise DiagnosticCaptureError("diagnostic path must not contain traversal")
        return path
