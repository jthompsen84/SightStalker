"""Transaction discipline tests (spec 19.11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from sightstalker.persistence import (
    PersistenceIntegrityError,
    ProfileRepository,
    RunRepository,
    SessionRepository,
)
from sightstalker.persistence.database import create_async_session_factory

from tests.persistence._factories import (
    PROFILE_ID,
    SESSION_ID,
    profile_record,
    run_record,
    session_record,
)


async def test_rollback_removes_rows(engine: AsyncEngine, tmp_path: Path) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        repo = ProfileRepository(s, data_dir=tmp_path / "data")
        await s.begin()
        await repo.create(profile_record(tmp_path / "data"))
        await s.rollback()
    async with factory() as s2:
        repo2 = ProfileRepository(s2, data_dir=tmp_path / "data")
        assert await repo2.get(PROFILE_ID) is None


async def test_commit_persists_rows(engine: AsyncEngine, tmp_path: Path) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        repo = ProfileRepository(s, data_dir=tmp_path / "data")
        async with s.begin():
            await repo.create(profile_record(tmp_path / "data"))
    async with factory() as s2:
        repo2 = ProfileRepository(s2, data_dir=tmp_path / "data")
        assert await repo2.get(PROFILE_ID) is not None


async def test_repository_methods_do_not_autocommit(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        repo = ProfileRepository(s, data_dir=tmp_path / "data")
        # No explicit begin()/commit(): create() flushes but must not commit.
        await repo.create(profile_record(tmp_path / "data"))
        # Roll back the pending (flushed-but-uncommitted) work.
        await s.rollback()
    async with factory() as s2:
        repo2 = ProfileRepository(s2, data_dir=tmp_path / "data")
        assert await repo2.get(PROFILE_ID) is None


async def test_mutating_methods_flush(engine: AsyncEngine, tmp_path: Path) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        repo = ProfileRepository(s, data_dir=tmp_path / "data")
        await s.begin()
        await repo.create(profile_record(tmp_path / "data"))
        # After flush the row is visible within the same uncommitted transaction.
        result = await s.execute(text("SELECT COUNT(*) FROM profiles"))
        assert result.scalar() == 1
        await s.rollback()


async def test_integrity_failure_raises_during_call(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        repo = ProfileRepository(s, data_dir=tmp_path / "data")
        async with s.begin():
            await repo.create(profile_record(tmp_path / "data"))
        with pytest.raises(PersistenceIntegrityError):
            async with s.begin():
                await repo.create(profile_record(tmp_path / "data"))


async def test_integrity_failure_rolls_back(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        repo = ProfileRepository(s, data_dir=tmp_path / "data")
        async with s.begin():
            await repo.create(profile_record(tmp_path / "data"))
        try:
            async with s.begin():
                await repo.create(
                    profile_record(tmp_path / "data", profile_id="prof_beta_def00000")
                )
                await repo.create(profile_record(tmp_path / "data"))  # dup -> error
        except PersistenceIntegrityError:
            pass
    async with factory() as s2:
        repo2 = ProfileRepository(s2, data_dir=tmp_path / "data")
        # The beta profile from the failed transaction must not persist.
        assert await repo2.get("prof_beta_def00000") is None


async def test_session_not_reused_across_tasks(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    # Each task gets its own session from the factory.
    factory = create_async_session_factory(engine)
    sessions: list[int] = []
    for _ in range(2):
        async with factory() as s:
            sessions.append(id(s))
    assert len(set(sessions)) == 2


async def test_two_sessions_read_committed(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as writer:
        repo = ProfileRepository(writer, data_dir=tmp_path / "data")
        async with writer.begin():
            await repo.create(profile_record(tmp_path / "data"))
    async with factory() as reader:
        repo2 = ProfileRepository(reader, data_dir=tmp_path / "data")
        assert await repo2.get(PROFILE_ID) is not None


async def test_uncommitted_not_visible_cross_session(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    # In-memory SQLite shares a single connection, so isolation is not
    # observable there; use a file DB to get genuinely separate connections.
    from sightstalker.persistence.database import (
        PersistenceConfig,
        create_async_engine,
    )
    from sightstalker.persistence.models import Base

    db = tmp_path / "isolation.db"
    cfg = PersistenceConfig(
        database_url=f"sqlite+aiosqlite:///{db}", data_dir=tmp_path / "data"
    )
    file_engine = create_async_engine(cfg)
    try:
        async with file_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = create_async_session_factory(file_engine)
        async with factory() as writer:
            repo = ProfileRepository(writer, data_dir=tmp_path / "data")
            await writer.begin()
            await repo.create(profile_record(tmp_path / "data"))
            # Not committed yet — a separate connection must not see it.
            async with factory() as reader:
                repo2 = ProfileRepository(reader, data_dir=tmp_path / "data")
                assert await repo2.get(PROFILE_ID) is None
            await writer.rollback()
    finally:
        await file_engine.dispose()


async def test_parent_delete_with_children_fails_no_cascade(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        async with s.begin():
            await ProfileRepository(s, data_dir=tmp_path / "data").create(
                profile_record(tmp_path / "data")
            )
            await SessionRepository(s).create(session_record())
            await RunRepository(s).create(run_record())
        # Deleting the parent session while a run references it must fail
        # (RESTRICT, no cascade).
        with pytest.raises(Exception):
            async with s.begin():
                await s.execute(
                    text("DELETE FROM sessions WHERE session_id = :sid"),
                    {"sid": SESSION_ID},
                )
