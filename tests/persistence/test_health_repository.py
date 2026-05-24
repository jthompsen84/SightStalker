"""Health repository tests (spec 19.10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sightstalker.models import SessionHealthRecord
from sightstalker.persistence import (
    HealthRepository,
    PersistenceIntegrityError,
    ProfileRepository,
    RunRepository,
    SessionRepository,
)

from tests.persistence._factories import (
    RUN_ID,
    SESSION_ID,
    health_record,
    profile_record,
    run_record,
    session_record,
)


async def _seed(session: AsyncSession, tmp_path: Path) -> None:
    await ProfileRepository(session, data_dir=tmp_path / "data").create(
        profile_record(tmp_path / "data")
    )
    await SessionRepository(session).create(session_record())


async def test_create_health_record(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        created = await HealthRepository(session).create(health_record())
    assert created.session_id == SESSION_ID


async def test_latest_for_session_orders_desc(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        repo = HealthRepository(session)
        await repo.create(health_record(status="healthy", reason="first"))
        await repo.create(health_record(status="degraded", reason="second"))
    latest = await HealthRepository(session).latest_for_session(SESSION_ID)
    assert latest is not None
    # Same created_at within the transaction -> tie-break by id DESC -> "second".
    assert latest.reason == "second"


async def test_list_for_session(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        repo = HealthRepository(session)
        await repo.create(health_record())
        await repo.create(health_record(status="degraded"))
    listed = await HealthRepository(session).list_for_session(SESSION_ID)
    assert len(listed) == 2


async def test_list_validates_positive_limit(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        await HealthRepository(session).list_for_session(SESSION_ID, limit=0)


async def test_missing_session_fk_fails(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await HealthRepository(session).create(health_record())


async def test_reason_sanitized(session: AsyncSession, tmp_path: Path) -> None:
    rec = health_record(reason="access_token=raw-token-123")
    async with session.begin():
        await _seed(session, tmp_path)
        created = await HealthRepository(session).create(rec)
    assert "raw-token-123" not in str(created.reason)


async def test_last_run_ids_round_trip(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
        rec = SessionHealthRecord(
            session_id=SESSION_ID,
            status="healthy",
            last_successful_run_id=RUN_ID,
        )
        await HealthRepository(session).create(rec)
    latest = await HealthRepository(session).latest_for_session(SESSION_ID)
    assert latest is not None and latest.last_successful_run_id == RUN_ID


async def test_no_raw_traceback_stored(
    session: AsyncSession, tmp_path: Path
) -> None:
    rec = health_record(
        reason="run failed: access_token=raw-token-123 refresh_token=refresh-token-abc"
    )
    async with session.begin():
        await _seed(session, tmp_path)
        await HealthRepository(session).create(rec)
    rows = (
        (await session.execute(text("SELECT reason FROM health_records")))
        .scalars()
        .all()
    )
    for stored in rows:
        assert "raw-token-123" not in str(stored)
        assert "refresh-token-abc" not in str(stored)


async def test_status_validates(session: AsyncSession, tmp_path: Path) -> None:
    bad = SessionHealthRecord.model_construct(
        session_id=SESSION_ID,
        status="not-a-real-status",  # type: ignore[arg-type]
        reason=None,
        last_successful_run_id=None,
        last_failed_run_id=None,
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await _seed(session, tmp_path)
            await HealthRepository(session).create(bad)


async def test_internal_id_not_surfaced(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        created = await HealthRepository(session).create(health_record())
    assert not hasattr(created, "id")
