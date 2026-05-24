"""Health service tests (spec §16)."""

from __future__ import annotations

import pytest

from sightstalker.diagnostics import HealthService
from sightstalker.diagnostics.errors import DiagnosticPersistenceError
from sightstalker.models import SessionHealthRecord

from tests.diagnostics.conftest import RecordingHealthRepo


def test_build_record_without_repo() -> None:
    service = HealthService()
    record = service.build_record(
        session_id="sess_alpha_default", status="healthy"
    )
    assert isinstance(record, SessionHealthRecord)
    assert record.status == "healthy"


def test_build_record_sanitizes_reason() -> None:
    service = HealthService()
    record = service.build_record(
        session_id="sess_alpha_default",
        status="degraded",
        reason="failure: access_token=raw-token-123",
    )
    assert record.reason is not None
    assert "raw-token-123" not in record.reason


def test_build_record_carries_run_ids() -> None:
    service = HealthService()
    record = service.build_record(
        session_id="sess_alpha_default",
        status="healthy",
        last_successful_run_id="run_auto_0123456789abcdef",
    )
    assert record.last_successful_run_id == "run_auto_0123456789abcdef"


async def test_persist_record_success() -> None:
    repo = RecordingHealthRepo()
    service = HealthService(health_persistence=repo)
    record = service.build_record(
        session_id="sess_alpha_default", status="healthy"
    )
    persisted = await service.persist_record(record)
    assert persisted.session_id == "sess_alpha_default"
    assert len(repo.created) == 1


async def test_persist_without_repo_raises() -> None:
    service = HealthService()
    record = service.build_record(
        session_id="sess_alpha_default", status="healthy"
    )
    with pytest.raises(DiagnosticPersistenceError):
        await service.persist_record(record)


async def test_persist_failure_wrapped() -> None:
    repo = RecordingHealthRepo(fail=True)
    service = HealthService(health_persistence=repo)
    record = service.build_record(
        session_id="sess_alpha_default", status="unhealthy"
    )
    with pytest.raises(DiagnosticPersistenceError) as excinfo:
        await service.persist_record(record)
    assert "boom" not in str(excinfo.value)


async def test_persist_resanitizes_raw_reason() -> None:
    repo = RecordingHealthRepo()
    service = HealthService(health_persistence=repo)
    # A raw record passed directly must be re-sanitized before storage.
    raw = SessionHealthRecord(
        session_id="sess_alpha_default",
        status="degraded",
        reason="token=raw-token-123",
    )
    await service.persist_record(raw)
    stored = repo.created[0]
    assert "raw-token-123" not in str(stored.reason)


def test_no_browser_probe_methods() -> None:
    service = HealthService()
    assert not hasattr(service, "probe")
    assert not hasattr(service, "check_network")
