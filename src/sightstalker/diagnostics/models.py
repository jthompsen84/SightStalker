"""
sightstalker.diagnostics.models — passive diagnostic value objects.

These models carry diagnostic intent and results. They never carry raw
payloads (screenshot/trace bytes or raw console text); console text is stored
already-redacted.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from sightstalker.models import (
    ArtifactRef,
    ContextId,
    JsonObject,
    RunId,
    SessionId,
    ToolkitModel,
)


class DiagnosticTarget(ToolkitModel):
    """Optional linkage describing what a diagnostic observation belongs to."""

    session_id: SessionId | None = None
    run_id: RunId | None = None
    context_id: ContextId | None = None
    run_order: int | None = Field(default=None, ge=0)


class DiagnosticPersistencePolicy(ToolkitModel):
    """Opt-in flags controlling whether diagnostics persist metadata."""

    persist_artifact_metadata: bool = False
    persist_health_record: bool = False


class ScreenshotOptions(ToolkitModel):
    """Options for a single screenshot capture."""

    full_page: bool = False
    timeout_ms: int | None = None
    filename_suffix: str = "screenshot.png"


class TraceOptions(ToolkitModel):
    """Options for a single trace capture."""

    name: str | None = None
    filename_suffix: str = "trace.zip"


class ConsoleEventRecord(ToolkitModel):
    """A single captured console event with already-redacted text."""

    event_type: str
    text_redacted: str
    location: JsonObject | None = None
    timestamp: datetime


class DiagnosticArtifactResult(ToolkitModel):
    """Result of a diagnostic artifact write, optionally persisted."""

    artifact_ref: ArtifactRef
    target: DiagnosticTarget
    persisted: bool = False
