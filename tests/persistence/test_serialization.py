"""Serialization/projection tests (spec 19.5)."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from sightstalker.models import (
    ArtifactRef,
    BrowserContextConfig,
    BrowserLaunchConfig,
    ProfileRecord,
    ProxyConfig,
    RunRecord,
    SessionConfig,
    utc_now,
)
from sightstalker.persistence.errors import (
    PersistenceIntegrityError,
    PersistenceSecurityError,
)
from sightstalker.persistence.serialization import (
    artifact_ref_to_row_values,
    canonical_json,
    persistable_session_config,
    profile_to_row_values,
    run_to_row_values,
    to_utc,
)


def _ref(path: str = "runs/r/out.json") -> ArtifactRef:
    return ArtifactRef(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="storage_state_initial",
        relative_path=Path(path),
        sha256="a" * 64,
        size_bytes=12,
        mime_type="application/json",
    )


def _safe_config() -> SessionConfig:
    return SessionConfig(
        launch=BrowserLaunchConfig(engine_name="mock"),
        context=BrowserContextConfig(),
    )


def test_artifact_ref_serializes() -> None:
    values = artifact_ref_to_row_values(
        _ref(), session_id=None, run_id=None, run_order=None
    )
    assert values["relative_path"] == "runs/r/out.json"
    assert values["sha256"] == "a" * 64


def test_artifact_ref_rejects_absolute_path() -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="storage_state_initial",
        relative_path=Path("/etc/passwd"),
        sha256="a" * 64,
        size_bytes=1,
        mime_type="application/json",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        artifact_ref_to_row_values(bad, session_id=None, run_id=None, run_order=None)


def test_artifact_ref_rejects_traversal() -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="storage_state_initial",
        relative_path=Path("..") / "escape.json",
        sha256="a" * 64,
        size_bytes=1,
        mime_type="application/json",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        artifact_ref_to_row_values(bad, session_id=None, run_id=None, run_order=None)


def test_artifact_ref_rejects_bad_sha() -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="storage_state_initial",
        relative_path=Path("runs/r/o.json"),
        sha256="ZZZ",
        size_bytes=1,
        mime_type="application/json",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        artifact_ref_to_row_values(bad, session_id=None, run_id=None, run_order=None)


def test_profile_serializes_without_active_lock_path(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    profile = ProfileRecord(
        profile_id="prof_alpha_default",
        name="alpha",
        profile_dir=data_dir / "profiles" / "prof_alpha_default",
        active_lock_path=Path("/tmp/should/not/persist.lock"),
    )
    values = profile_to_row_values(profile, data_dir=data_dir)
    assert "active_lock_path" not in values


def test_absolute_profile_dir_under_data_dir_stored_relative(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    profile = ProfileRecord(
        profile_id="prof_alpha_default",
        name="alpha",
        profile_dir=data_dir / "profiles" / "prof_alpha_default",
    )
    values = profile_to_row_values(profile, data_dir=data_dir)
    assert values["profile_dir"] == "profiles/prof_alpha_default"


def test_absolute_profile_dir_outside_data_dir_rejected(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    outside = tmp_path / "elsewhere" / "p"
    profile = ProfileRecord(
        profile_id="prof_alpha_default", name="alpha", profile_dir=outside
    )
    with pytest.raises(PersistenceSecurityError):
        profile_to_row_values(profile, data_dir=data_dir)


def test_safe_session_config_projects() -> None:
    projection = persistable_session_config(_safe_config())
    assert projection["launch"]["engine_name"] == "mock"  # type: ignore[index]
    assert "env" not in projection["launch"]  # type: ignore[operator]


def test_session_config_proxy_password_rejected() -> None:
    cfg = SessionConfig(
        launch=BrowserLaunchConfig(
            engine_name="mock",
            proxy=ProxyConfig(server="http://p", password=SecretStr("p-123")),
        ),
        context=BrowserContextConfig(),
    )
    with pytest.raises(PersistenceSecurityError):
        persistable_session_config(cfg)


def test_proxy_password_rejected_despite_masked_dump() -> None:
    cfg = SessionConfig(
        launch=BrowserLaunchConfig(
            engine_name="mock",
            proxy=ProxyConfig(server="http://p", password=SecretStr("p-123")),
        ),
        context=BrowserContextConfig(),
    )
    dumped = cfg.model_dump(mode="json")
    # model_dump masks the secret, proving dump-based detection is insufficient.
    assert "p-123" not in str(dumped)
    with pytest.raises(PersistenceSecurityError):
        persistable_session_config(cfg)


def test_session_config_nonempty_env_rejected() -> None:
    cfg = SessionConfig(
        launch=BrowserLaunchConfig(engine_name="mock", env={"SECRET": "x"}),
        context=BrowserContextConfig(),
    )
    with pytest.raises(PersistenceSecurityError):
        persistable_session_config(cfg)


def test_session_config_sensitive_headers_rejected() -> None:
    cfg = SessionConfig(
        launch=BrowserLaunchConfig(engine_name="mock"),
        context=BrowserContextConfig(
            extra_http_headers={"Authorization": "Bearer raw-secret"}
        ),
    )
    with pytest.raises(PersistenceSecurityError):
        persistable_session_config(cfg)


def test_session_config_path_fields_rejected(tmp_path: Path) -> None:
    cfg = SessionConfig(
        launch=BrowserLaunchConfig(
            engine_name="mock", executable_path=tmp_path / "browser"
        ),
        context=BrowserContextConfig(),
    )
    with pytest.raises(PersistenceSecurityError):
        persistable_session_config(cfg)

    cfg2 = SessionConfig(
        launch=BrowserLaunchConfig(engine_name="mock"),
        context=BrowserContextConfig(record_har_path=tmp_path / "har.har"),
    )
    with pytest.raises(PersistenceSecurityError):
        persistable_session_config(cfg2)


def test_run_metadata_redacted() -> None:
    run = RunRecord(
        run_id="run_auto_0123456789abcdef",
        session_id="sess_alpha_default",
        metadata={"access_token": "raw-token-123", "page": "home"},
    )
    values = run_to_row_values(run)
    assert "raw-token-123" not in str(values["metadata_json"])
    assert "home" in str(values["metadata_json"])


def test_run_start_url_with_credentials_rejected() -> None:
    run = RunRecord(
        run_id="run_auto_0123456789abcdef",
        session_id="sess_alpha_default",
        start_url="https://user:pass@example.com/path",
    )
    with pytest.raises(PersistenceSecurityError):
        run_to_row_values(run)


def test_timestamps_timezone_aware() -> None:
    now = utc_now()
    converted = to_utc(now)
    assert converted.tzinfo is not None
    assert converted.tzinfo == timezone.utc or converted.utcoffset() is not None


def test_canonical_json_deterministic() -> None:
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(PersistenceIntegrityError):
        canonical_json({"x": float("nan")})
