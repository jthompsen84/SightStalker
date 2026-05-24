"""Run + browser-context repository tests (spec 19.8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sightstalker.models import utc_now
from sightstalker.persistence import (
    ArtifactRepository,
    BrowserContextRepository,
    PersistenceIntegrityError,
    PersistenceSecurityError,
    ProfileRepository,
    RunRepository,
    SessionRepository,
)

from tests.persistence._factories import (
    CONTEXT_ID,
    RUN_ID,
    SESSION_ID,
    artifact_ref,
    context_record,
    profile_record,
    run_record,
    session_record,
)


async def _seed(session: AsyncSession, tmp_path: Path) -> None:
    await ProfileRepository(session, data_dir=tmp_path / "data").create(
        profile_record(tmp_path / "data")
    )
    await SessionRepository(session).create(session_record())


async def test_create_run(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        created = await RunRepository(session).create(run_record())
    assert created.run_id == RUN_ID


async def test_create_run_missing_session_fails(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await RunRepository(session).create(run_record())


async def test_get_run(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
    got = await RunRepository(session).get(RUN_ID)
    assert got is not None and got.run_id == RUN_ID


async def test_list_runs_for_session(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
    listed = await RunRepository(session).list_for_session(SESSION_ID)
    assert len(listed) == 1


async def test_list_runs_validates_limit(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        await RunRepository(session).list_for_session(SESSION_ID, limit=0)


async def test_update_run_status(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        created = await RunRepository(session).create(run_record())
        updated = await RunRepository(session).update(
            created.model_copy(update={"status": "succeeded"})
        )
    assert updated.status == "succeeded"
    assert updated.updated_at is not None


async def test_timestamps_round_trip(session: AsyncSession, tmp_path: Path) -> None:
    now = utc_now()
    run = run_record().model_copy(update={"started_at": now, "completed_at": now})
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run)
    got = await RunRepository(session).require(RUN_ID)
    assert got.started_at is not None and got.started_at.tzinfo is not None
    assert got.completed_at is not None and got.completed_at.tzinfo is not None


async def test_redacted_error_round_trips(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record().model_copy(
        update={"error_type": "ValueError", "error_message_redacted": "boom"}
    )
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run)
    got = await RunRepository(session).require(RUN_ID)
    assert got.error_type == "ValueError"
    assert got.error_message_redacted == "boom"


async def test_no_raw_error_message_column(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
    cols = (await session.execute(text("PRAGMA table_info(runs)"))).fetchall()
    names = {c[1] for c in cols}
    assert "error_message" not in names
    assert "error_message_redacted" in names


async def test_run_metadata_redacted(session: AsyncSession, tmp_path: Path) -> None:
    run = run_record(metadata={"access_token": "raw-token-123", "page": "home"})
    async with session.begin():
        await _seed(session, tmp_path)
        created = await RunRepository(session).create(run)
    assert created.metadata["access_token"] == "<redacted>"
    assert created.metadata["page"] == "home"


async def test_create_returns_sanitized_metadata(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record(metadata={"refresh_token": "secret-abc"})
    async with session.begin():
        await _seed(session, tmp_path)
        created = await RunRepository(session).create(run)
    assert "secret-abc" not in str(created.metadata)


async def test_get_equals_sanitized_created(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record(metadata={"access_token": "raw-token-123", "page": "home"})
    async with session.begin():
        await _seed(session, tmp_path)
        created = await RunRepository(session).create(run)
    got = await RunRepository(session).require(RUN_ID)
    assert got.metadata == created.metadata


async def test_run_artifacts_rehydrate_in_order(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
        art_repo = ArtifactRepository(session)
        await art_repo.create(
            artifact_ref(artifact_id="art_b_0123456789abcdef", path="r/b.json"),
            run_id=RUN_ID,
            run_order=1,
        )
        await art_repo.create(
            artifact_ref(artifact_id="art_a_0123456789abcdef", path="r/a.json"),
            run_id=RUN_ID,
            run_order=0,
        )
    got = await RunRepository(session).require(RUN_ID)
    ids = [a.artifact_id for a in got.artifacts]
    assert ids == ["art_a_0123456789abcdef", "art_b_0123456789abcdef"]


async def test_run_repo_does_not_create_artifact_rows(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record().model_copy(update={"artifacts": (artifact_ref(),)})
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run)
    # The artifact embedded in RunRecord.artifacts must NOT have been inserted.
    rows = (await session.execute(text("SELECT COUNT(*) FROM artifacts"))).scalar()
    assert rows == 0


async def test_create_browser_context(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
        created = await BrowserContextRepository(session).create(context_record())
    assert created.context_id == CONTEXT_ID


async def test_context_storage_refs_round_trip(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
        ref = await ArtifactRepository(session).create(
            artifact_ref(), session_id=SESSION_ID
        )
        ctx = context_record().model_copy(
            update={"initial_storage_state": ref}
        )
        await BrowserContextRepository(session).create(ctx)
    got = await BrowserContextRepository(session).require(CONTEXT_ID)
    assert got.initial_storage_state is not None
    assert got.initial_storage_state.artifact_id == ref.artifact_id


async def test_missing_run_fk_for_context_fails(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await _seed(session, tmp_path)
            await BrowserContextRepository(session).create(context_record())


async def test_closed_timestamp_round_trips(
    session: AsyncSession, tmp_path: Path
) -> None:
    now = utc_now()
    async with session.begin():
        await _seed(session, tmp_path)
        await RunRepository(session).create(run_record())
        ctx = context_record().model_copy(update={"closed_at": now})
        await BrowserContextRepository(session).create(ctx)
    got = await BrowserContextRepository(session).require(CONTEXT_ID)
    assert got.closed_at is not None and got.closed_at.tzinfo is not None


async def test_start_url_with_credentials_rejected(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record().model_copy(
        update={"start_url": "https://user:pass@example.com/x"}
    )
    with pytest.raises(PersistenceSecurityError):
        async with session.begin():
            await _seed(session, tmp_path)
            await RunRepository(session).create(run)
