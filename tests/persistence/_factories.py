"""Shared record builders for persistence repository tests."""

from __future__ import annotations

from pathlib import Path

from sightstalker.models import (
    ArtifactRef,
    BrowserContextConfig,
    BrowserContextRecord,
    BrowserLaunchConfig,
    ProfileRecord,
    RunRecord,
    SessionConfig,
    SessionHealthRecord,
    SessionRecord,
)

PROFILE_ID = "prof_alpha_default"
SESSION_ID = "sess_alpha_default"
RUN_ID = "run_auto_0123456789abcdef"
CONTEXT_ID = "ctx_auto_0123456789ab"


def profile_record(data_dir: Path, *, profile_id: str = PROFILE_ID) -> ProfileRecord:
    return ProfileRecord(
        profile_id=profile_id,
        name="alpha",
        profile_dir=data_dir / "profiles" / profile_id,
    )


def safe_session_config() -> SessionConfig:
    return SessionConfig(
        launch=BrowserLaunchConfig(engine_name="mock"),
        context=BrowserContextConfig(),
    )


def session_record(
    *, session_id: str = SESSION_ID, profile_id: str = PROFILE_ID
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        name="s",
        profile_id=profile_id,
        config=safe_session_config(),
    )


def run_record(
    *,
    run_id: str = RUN_ID,
    session_id: str = SESSION_ID,
    status: str = "running",
    metadata: dict[str, object] | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        session_id=session_id,
        status=status,  # type: ignore[arg-type]
        metadata=metadata or {},
    )


def context_record(
    *,
    context_id: str = CONTEXT_ID,
    run_id: str = RUN_ID,
    session_id: str = SESSION_ID,
) -> BrowserContextRecord:
    return BrowserContextRecord(
        context_id=context_id,
        run_id=run_id,
        session_id=session_id,
    )


def artifact_ref(
    *,
    artifact_id: str = "art_init_0123456789abcdef",
    artifact_type: str = "storage_state_initial",
    path: str = "profiles/p/runs/r/storage_state.initial.json",
) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,  # type: ignore[arg-type]
        relative_path=Path(path),
        sha256="a" * 64,
        size_bytes=10,
        mime_type="application/json",
    )


def health_record(
    *,
    session_id: str = SESSION_ID,
    status: str = "healthy",
    reason: str | None = None,
) -> SessionHealthRecord:
    return SessionHealthRecord(
        session_id=session_id,
        status=status,  # type: ignore[arg-type]
        reason=reason,
    )
