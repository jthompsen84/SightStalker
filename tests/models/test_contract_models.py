"""
Contract model tests for FOUNDATION-CONTRACT-1.

Verifies:
- Immutability and field rejection semantics of ToolkitModel
- MutableToolkitModel assignment validation
- Repr exclusion of sensitive fields
- BrowserState tuple immutability
- SHA-256 validation on ArtifactRef
- StorageStateArtifact type constraint
- RunRecord/RunResult error field naming
- Identifier pattern acceptance/rejection
- Test fixture ID validity
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sightstalker.models import (
    ArtifactRef,
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
    FingerprintConfig,
    MutableToolkitModel,
    ProfileRecord,
    ProxyConfig,
    RunRecord,
    RunRequest,
    RunResult,
    ScreenshotArtifact,
    SessionConfig,
    SessionRecord,
    StorageStateArtifact,
    TimestampedModel,
    ToolkitModel,
    TraceArtifact,
    utc_now,
)
from sightstalker.models.identifiers import (
    ArtifactId,
    ContextId,
    ProfileId,
    RunId,
    SessionId,
)

# ---------------------------------------------------------------------------
# Test fixture IDs (satisfy normal patterns, signal test identity by name)
# ---------------------------------------------------------------------------

PROF_ID: ProfileId = "prof_test_default"
SESS_ID: SessionId = "sess_test_default"
RUN_ID: RunId = "run_test_default"
CTX_ID: ContextId = "ctx_test_default"
ART_ID: ArtifactId = "art_test_default"
VALID_SHA256 = "a" * 64


def _minimal_launch_config() -> BrowserLaunchConfig:
    return BrowserLaunchConfig()


def _minimal_context_config() -> BrowserContextConfig:
    return BrowserContextConfig()


def _minimal_session_config() -> SessionConfig:
    return SessionConfig(
        launch=_minimal_launch_config(),
        context=_minimal_context_config(),
    )


def _minimal_artifact_ref(artifact_type: str = "screenshot") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=ART_ID,
        artifact_type=artifact_type,  # type: ignore[arg-type]
        relative_path=Path("runs/run_test_default/screenshot.png"),
        sha256=VALID_SHA256,
        size_bytes=1024,
    )


# ---------------------------------------------------------------------------
# 1. ToolkitModel rejects unknown fields
# ---------------------------------------------------------------------------


def test_toolkit_model_rejects_unknown_fields() -> None:
    class _Sample(ToolkitModel):
        x: int

    with pytest.raises(ValidationError) as exc_info:
        _Sample(x=1, unknown_field="oops")  # type: ignore[call-arg]

    assert "unknown_field" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. ToolkitModel is frozen
# ---------------------------------------------------------------------------


def test_toolkit_model_is_frozen() -> None:
    class _Sample(ToolkitModel):
        x: int = 1

    obj = _Sample()
    with pytest.raises((ValidationError, TypeError)):
        obj.x = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. MutableToolkitModel allows validated assignment
# ---------------------------------------------------------------------------


def test_mutable_toolkit_model_allows_assignment_validation() -> None:
    class _Counter(MutableToolkitModel):
        value: int = 0

    counter = _Counter()
    counter.value = 42
    assert counter.value == 42


def test_mutable_toolkit_model_validates_on_assignment() -> None:
    class _Counter(MutableToolkitModel):
        value: int = 0

    counter = _Counter()
    with pytest.raises(ValidationError):
        counter.value = "not-an-int"  # type: ignore[assignment]


def test_mutable_toolkit_model_rejects_unknown_fields() -> None:
    class _Counter(MutableToolkitModel):
        value: int = 0

    with pytest.raises(ValidationError):
        _Counter(value=1, surprise=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 4. TimestampedModel.created_at is timezone-aware
# ---------------------------------------------------------------------------


def test_timestamped_model_created_at_is_timezone_aware() -> None:
    obj = TimestampedModel()
    assert obj.created_at.tzinfo is not None


def test_utc_now_is_timezone_aware() -> None:
    ts = utc_now()
    assert ts.tzinfo is not None


# ---------------------------------------------------------------------------
# 5–6. BrowserLaunchConfig defaults and repr exclusions
# ---------------------------------------------------------------------------


def test_browser_launch_config_defaults() -> None:
    cfg = BrowserLaunchConfig()
    assert cfg.engine_name == "camoufox"
    assert cfg.mode == "headless"


def test_browser_launch_config_env_not_in_repr() -> None:
    cfg = BrowserLaunchConfig(env={"SECRET_TOKEN": "abc123"})
    assert "abc123" not in repr(cfg)
    assert "SECRET_TOKEN" not in repr(cfg)


# ---------------------------------------------------------------------------
# 7. ProxyConfig.password not in repr
# ---------------------------------------------------------------------------


def test_proxy_config_password_not_in_repr() -> None:
    from pydantic import SecretStr

    proxy = ProxyConfig(server="http://proxy.example.com", password=SecretStr("s3cr3t"))
    assert "s3cr3t" not in repr(proxy)


# ---------------------------------------------------------------------------
# 8. FingerprintConfig.user_agent not in repr
# ---------------------------------------------------------------------------


def test_fingerprint_config_user_agent_not_in_repr() -> None:
    fp = FingerprintConfig(user_agent="Mozilla/5.0 (test agent)")
    assert "Mozilla/5.0" not in repr(fp)
    assert "test agent" not in repr(fp)


# ---------------------------------------------------------------------------
# 9. BrowserContextConfig.extra_http_headers not in repr
# ---------------------------------------------------------------------------


def test_browser_context_config_extra_http_headers_not_in_repr() -> None:
    cfg = BrowserContextConfig(
        extra_http_headers={"Authorization": "Bearer tok_secret"}
    )
    assert "tok_secret" not in repr(cfg)
    assert "Bearer" not in repr(cfg)


# ---------------------------------------------------------------------------
# 10–12. BrowserState immutability
# ---------------------------------------------------------------------------


def test_browser_state_cookies_is_tuple() -> None:
    state = BrowserState(engine_name="mock")
    assert isinstance(state.cookies, tuple)


def test_browser_state_origins_is_tuple() -> None:
    state = BrowserState(engine_name="mock")
    assert isinstance(state.origins, tuple)


def test_browser_state_cookies_tuple_prevents_append() -> None:
    state = BrowserState(engine_name="mock")
    with pytest.raises(AttributeError):
        state.cookies.append({"name": "evil"})  # type: ignore[attr-defined]


def test_browser_state_rejects_field_reassignment() -> None:
    state = BrowserState(engine_name="mock")
    with pytest.raises((ValidationError, TypeError)):
        state.engine_name = "camoufox"  # type: ignore[misc]


def test_browser_state_cookies_not_in_repr() -> None:
    state = BrowserState(
        engine_name="mock",
        cookies=({"name": "session_id", "value": "topsecret"},),
    )
    assert "topsecret" not in repr(state)


# ---------------------------------------------------------------------------
# 13–14. ArtifactRef SHA-256 validation
# ---------------------------------------------------------------------------


def test_artifact_ref_rejects_invalid_sha256() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(
            artifact_id=ART_ID,
            artifact_type="screenshot",
            relative_path=Path("runs/run_test_default/screenshot.png"),
            sha256="not-a-valid-hash",
            size_bytes=512,
        )


def test_artifact_ref_rejects_uppercase_sha256() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(
            artifact_id=ART_ID,
            artifact_type="screenshot",
            relative_path=Path("runs/run_test_default/screenshot.png"),
            sha256="A" * 64,  # uppercase invalid
            size_bytes=512,
        )


def test_artifact_ref_accepts_valid_sha256() -> None:
    ref = ArtifactRef(
        artifact_id=ART_ID,
        artifact_type="screenshot",
        relative_path=Path("runs/run_test_default/screenshot.png"),
        sha256=VALID_SHA256,
        size_bytes=512,
    )
    assert ref.sha256 == VALID_SHA256


# ---------------------------------------------------------------------------
# 15–17. StorageStateArtifact type constraint
# ---------------------------------------------------------------------------


def test_storage_state_artifact_accepts_initial() -> None:
    artifact = StorageStateArtifact(
        artifact_id=ART_ID,
        artifact_type="storage_state_initial",
        relative_path=Path("runs/run_test_default/storage_state.initial.json"),
        sha256=VALID_SHA256,
        size_bytes=256,
    )
    assert artifact.artifact_type == "storage_state_initial"


def test_storage_state_artifact_accepts_final() -> None:
    artifact = StorageStateArtifact(
        artifact_id=ART_ID,
        artifact_type="storage_state_final",
        relative_path=Path("runs/run_test_default/storage_state.final.json"),
        sha256=VALID_SHA256,
        size_bytes=256,
    )
    assert artifact.artifact_type == "storage_state_final"


def test_storage_state_artifact_rejects_screenshot_type() -> None:
    with pytest.raises(ValidationError):
        StorageStateArtifact(
            artifact_id=ART_ID,
            artifact_type="screenshot",  # type: ignore[arg-type]
            relative_path=Path("runs/run_test_default/screenshot.png"),
            sha256=VALID_SHA256,
            size_bytes=512,
        )


def test_storage_state_artifact_rejects_trace_type() -> None:
    with pytest.raises(ValidationError):
        StorageStateArtifact(
            artifact_id=ART_ID,
            artifact_type="trace",  # type: ignore[arg-type]
            relative_path=Path("runs/run_test_default/trace.zip"),
            sha256=VALID_SHA256,
            size_bytes=512,
        )


# ---------------------------------------------------------------------------
# 18–19. Subtype artifact_type defaults
# ---------------------------------------------------------------------------


def test_screenshot_artifact_type_is_screenshot() -> None:
    artifact = ScreenshotArtifact(
        artifact_id=ART_ID,
        relative_path=Path("runs/run_test_default/screenshot.png"),
        sha256=VALID_SHA256,
        size_bytes=512,
    )
    assert artifact.artifact_type == "screenshot"


def test_trace_artifact_type_is_trace() -> None:
    artifact = TraceArtifact(
        artifact_id=ART_ID,
        relative_path=Path("runs/run_test_default/trace.zip"),
        sha256=VALID_SHA256,
        size_bytes=1024,
    )
    assert artifact.artifact_type == "trace"


# ---------------------------------------------------------------------------
# 20–21. RunRecord ID and error field semantics
# ---------------------------------------------------------------------------


def test_run_record_keeps_run_id_and_session_id_distinct() -> None:
    record = RunRecord(run_id=RUN_ID, session_id=SESS_ID)
    assert record.run_id == RUN_ID
    assert record.session_id == SESS_ID
    assert record.run_id != record.session_id


def test_run_record_has_error_message_redacted_field() -> None:
    record = RunRecord(
        run_id=RUN_ID,
        session_id=SESS_ID,
        status="failed",
        error_type="NavigationError",
        error_message_redacted="Navigation timed out after 30s",
    )
    assert record.error_message_redacted == "Navigation timed out after 30s"
    # Verify the raw field name does not exist
    assert not hasattr(record, "error_message")


def test_run_result_has_error_message_redacted_field() -> None:
    result = RunResult(
        run_id=RUN_ID,
        session_id=SESS_ID,
        status="failed",
        error_type="NavigationError",
        error_message_redacted="Timed out",
    )
    assert result.error_message_redacted == "Timed out"
    assert not hasattr(result, "error_message")


# ---------------------------------------------------------------------------
# 22. Test fixture IDs validate against normal patterns
# ---------------------------------------------------------------------------


def test_fixture_profile_id_is_valid() -> None:
    record = ProfileRecord(
        profile_id=PROF_ID,
        name="Test Profile",
        profile_dir=Path("/tmp/test_profile"),
    )
    assert record.profile_id == PROF_ID


def test_fixture_session_id_is_valid() -> None:
    record = RunRequest(session_id=SESS_ID)
    assert record.session_id == SESS_ID


def test_fixture_run_id_is_valid() -> None:
    record = RunRecord(run_id=RUN_ID, session_id=SESS_ID)
    assert record.run_id == RUN_ID


def test_fixture_artifact_id_is_valid() -> None:
    ref = _minimal_artifact_ref()
    assert ref.artifact_id == ART_ID


def test_fixture_session_record_is_valid() -> None:
    record = SessionRecord(
        session_id=SESS_ID,
        name="default",
        profile_id=PROF_ID,
        config=_minimal_session_config(),
    )
    assert record.session_id == SESS_ID
    assert record.profile_id == PROF_ID


# ---------------------------------------------------------------------------
# 23. Invalid identifier prefixes are rejected
# ---------------------------------------------------------------------------


def test_invalid_profile_id_prefix_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileRecord(
            profile_id="session_not_a_profile",  # type: ignore[arg-type]
            name="Bad",
            profile_dir=Path("/tmp/bad"),
        )


def test_invalid_run_id_prefix_rejected() -> None:
    with pytest.raises(ValidationError):
        RunRecord(
            run_id="sess_wrong_prefix",  # type: ignore[arg-type]
            session_id=SESS_ID,
        )


def test_invalid_session_id_too_short_rejected() -> None:
    with pytest.raises(ValidationError):
        RunRequest(session_id="sess_x")  # type: ignore[arg-type]


def test_session_record_is_frozen() -> None:
    record = SessionRecord(
        session_id=SESS_ID,
        name="default",
        profile_id=PROF_ID,
        config=_minimal_session_config(),
    )
    with pytest.raises((ValidationError, TypeError)):
        record.name = "mutated"  # type: ignore[misc]
