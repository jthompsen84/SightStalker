from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from sightstalker.models.base import TimestampedModel, ToolkitModel
from sightstalker.models.identifiers import (
    ArtifactId,
    ArtifactType,
    HashAlgorithm,
    RunId,
    SessionId,
    StorageStateArtifactType,
)

# ---------------------------------------------------------------------------
# Artifact reference (lightweight pointer, stored in DB and run records)
# ---------------------------------------------------------------------------


class ArtifactRef(ToolkitModel):
    """
    Lightweight, immutable reference to an artifact file.

    relative_path must be a relative path. Absolute path enforcement is
    implemented in the ArtifactManager (ARTIFACTS-1). This model names the
    field correctly and validates the SHA-256 pattern.
    """

    artifact_id: ArtifactId
    artifact_type: ArtifactType
    relative_path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    mime_type: str | None = None
    hash_algorithm: HashAlgorithm = "sha256"


# ---------------------------------------------------------------------------
# Diagnostic artifact records (full provenance, stored by ArtifactManager)
# ---------------------------------------------------------------------------


class DiagnosticArtifact(TimestampedModel):
    """
    Full provenance record for a diagnostic artifact.

    redacted=True by default signals that any sensitive fields have been
    sanitized before this record was constructed.
    """

    artifact_id: ArtifactId
    artifact_type: ArtifactType
    session_id: SessionId | None = None
    run_id: RunId | None = None
    relative_path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    mime_type: str | None = None
    description: str | None = None
    redacted: bool = True


class ScreenshotArtifact(DiagnosticArtifact):
    """Diagnostic artifact record for a screenshot."""

    artifact_type: Literal["screenshot"] = "screenshot"  # type: ignore[assignment]
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    full_page: bool = False


class TraceArtifact(DiagnosticArtifact):
    """Diagnostic artifact record for a Playwright trace archive."""

    artifact_type: Literal["trace"] = "trace"  # type: ignore[assignment]
    trace_format: str = "playwright_trace_zip"


class StorageStateArtifact(DiagnosticArtifact):
    """
    Diagnostic artifact record for a browser storage state snapshot.

    artifact_type is constrained to storage-state variants only.
    Accepts "storage_state_initial" or "storage_state_final".
    Rejects all other ArtifactType values at validation time.
    """

    artifact_type: StorageStateArtifactType  # type: ignore[assignment]
    engine_state_schema: str = "browser_state_v1"
