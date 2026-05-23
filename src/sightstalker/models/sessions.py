from __future__ import annotations

from pathlib import Path

from pydantic import Field

from sightstalker.models.artifacts import ArtifactRef
from sightstalker.models.base import TimestampedModel, ToolkitModel
from sightstalker.models.browser import BrowserContextConfig, BrowserLaunchConfig
from sightstalker.models.identifiers import (
    FingerprintProfileId,
    HealthStatus,
    ProfileId,
    ProxyProfileId,
    RunId,
    SessionId,
)

# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class ProfileRecord(TimestampedModel):
    """
    Persistent browser identity container.

    A profile owns a user-data directory and may reference fingerprint and
    proxy profiles. A profile is not a session and is not a run.

    Profile locking behavior (one-profile-one-active-run invariant) is
    implemented in SESSION-STATE-1, not here.
    """

    profile_id: ProfileId
    name: str
    profile_dir: Path
    fingerprint_profile_id: FingerprintProfileId | None = None
    proxy_profile_id: ProxyProfileId | None = None
    active_lock_path: Path | None = None
    health_status: HealthStatus = "unknown"
    archived: bool = False


# ---------------------------------------------------------------------------
# Session configuration
# ---------------------------------------------------------------------------


class SessionConfig(ToolkitModel):
    """
    Stable logical session configuration.

    A session binds launch and context defaults to a profile. It does not
    represent one execution attempt (that is a Run).
    """

    launch: BrowserLaunchConfig
    context: BrowserContextConfig
    persist_storage_state: bool = True
    capture_initial_storage_state: bool = True
    capture_final_storage_state: bool = True
    screenshot_on_failure: bool = True
    trace_on_failure: bool = True


# ---------------------------------------------------------------------------
# Session record
# ---------------------------------------------------------------------------


class SessionRecord(TimestampedModel):
    """
    Durable record of a named session binding a config to a profile.

    Sessions are reused across many runs. latest_initial_state and
    latest_final_state reference the most recent storage-state artifacts
    for quick inspection; full artifact history is stored in the DB.
    """

    session_id: SessionId
    name: str
    profile_id: ProfileId
    config: SessionConfig
    latest_initial_state: ArtifactRef | None = None
    latest_final_state: ArtifactRef | None = None
    health_status: HealthStatus = "unknown"
    archived: bool = False


# ---------------------------------------------------------------------------
# Session health record
# ---------------------------------------------------------------------------


class SessionHealthRecord(TimestampedModel):
    """
    Point-in-time health observation for a session.

    last_successful_run_id and last_failed_run_id are typed as RunId | None
    to enforce the run ID pattern at the model boundary.
    """

    session_id: SessionId
    status: HealthStatus
    reason: str | None = None
    last_successful_run_id: RunId | None = Field(default=None)
    last_failed_run_id: RunId | None = Field(default=None)
