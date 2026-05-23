from __future__ import annotations

from datetime import datetime

from pydantic import Field

from sightstalker.models.artifacts import ArtifactRef
from sightstalker.models.base import JsonObject, TimestampedModel, ToolkitModel
from sightstalker.models.identifiers import (
    ContextId,
    RunId,
    RunStatus,
    SessionId,
)

# ---------------------------------------------------------------------------
# Run request (command object)
# ---------------------------------------------------------------------------


class RunRequest(ToolkitModel):
    """
    Immutable command object for one execution attempt.

    A RunRequest is the input to a run. It does not execute anything.
    Execution behavior is implemented in the SessionManager / RunLifecycleManager
    (SESSION-STATE-1).
    """

    session_id: SessionId
    start_url: str | None = None
    headed_override: bool | None = None
    timeout_ms: int = Field(default=120_000, ge=1_000, le=3_600_000)
    metadata: JsonObject = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Browser context record
# ---------------------------------------------------------------------------


class BrowserContextRecord(TimestampedModel):
    """
    Durable record of one browser isolation context created during a run.

    A context belongs to one run. It may reference initial and final
    storage-state artifacts. closed_at is set when the context closes;
    since the model is frozen, context records are reconstructed (not
    mutated) to reflect the closed state.
    """

    context_id: ContextId
    run_id: RunId
    session_id: SessionId
    initial_storage_state: ArtifactRef | None = None
    final_storage_state: ArtifactRef | None = None
    closed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------


class RunRecord(TimestampedModel):
    """
    Durable record of one execution attempt.

    Distinguishes run_id from session_id — these are never conflated.

    Error fields use error_message_redacted to make explicit that raw
    exception strings must be sanitized before being stored. Raw exception
    text must not appear in this model.
    """

    run_id: RunId
    session_id: SessionId
    status: RunStatus = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    start_url: str | None = None
    error_type: str | None = None
    error_message_redacted: str | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    metadata: JsonObject = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Run result (output value object)
# ---------------------------------------------------------------------------


class RunResult(ToolkitModel):
    """
    Immutable output value from a completed run.

    Returned by the run lifecycle manager. Error fields mirror RunRecord
    semantics: only redacted error text is carried forward.
    """

    run_id: RunId
    session_id: SessionId
    status: RunStatus
    artifacts: tuple[ArtifactRef, ...] = ()
    error_type: str | None = None
    error_message_redacted: str | None = None
