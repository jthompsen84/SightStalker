"""Database config/engine/session tests (spec 19.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sightstalker.persistence.database import (
    PersistenceConfig,
    create_async_engine,
    create_async_session_factory,
    database_session,
    sanitize_database_url,
)
from sightstalker.persistence.models import Base


def test_config_accepts_sqlite_async_url(tmp_path: Path) -> None:
    cfg = PersistenceConfig(
        database_url="sqlite+aiosqlite:///x.db", data_dir=tmp_path
    )
    assert cfg.database_url == "sqlite+aiosqlite:///x.db"


def test_config_does_not_expose_url_in_repr(tmp_path: Path) -> None:
    cfg = PersistenceConfig(
        database_url="sqlite+aiosqlite:///secret.db", data_dir=tmp_path
    )
    assert "secret.db" not in repr(cfg)


def test_config_requires_data_dir(tmp_path: Path) -> None:
    cfg = PersistenceConfig(
        database_url="sqlite+aiosqlite:///x.db", data_dir=tmp_path
    )
    assert cfg.data_dir == tmp_path


def test_sanitize_database_url_removes_credentials() -> None:
    out = sanitize_database_url("postgresql+asyncpg://user:pass@host:5432/db")
    assert "pass" not in out
    assert "user" not in out
    assert "host" in out


def test_sanitize_database_url_passthrough_no_creds() -> None:
    url = "sqlite+aiosqlite:///local.db"
    assert sanitize_database_url(url) == url


def test_create_async_engine_returns_async_engine(tmp_path: Path) -> None:
    cfg = PersistenceConfig(
        database_url="sqlite+aiosqlite:///:memory:", data_dir=tmp_path
    )
    eng = create_async_engine(cfg)
    assert isinstance(eng, AsyncEngine)


def test_create_session_factory(engine: AsyncEngine) -> None:
    factory = create_async_session_factory(engine)
    assert isinstance(factory, async_sessionmaker)


async def test_database_session_opens_and_closes(engine: AsyncEngine) -> None:
    factory = create_async_session_factory(engine)
    async with database_session(factory) as s:
        assert isinstance(s, AsyncSession)
        result = await s.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_sqlite_foreign_keys_enabled(engine: AsyncEngine) -> None:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        result = await s.execute(text("PRAGMA foreign_keys"))
        assert result.scalar() == 1


async def test_sqlite_foreign_keys_on_fresh_pooled_connection(
    tmp_path: Path,
) -> None:
    cfg = PersistenceConfig(
        database_url="sqlite+aiosqlite:///:memory:", data_dir=tmp_path
    )
    eng = create_async_engine(cfg)
    try:
        # Two separate connections both must have the pragma applied.
        for _ in range(2):
            async with eng.connect() as conn:
                result = await conn.execute(text("PRAGMA foreign_keys"))
                assert result.scalar() == 1
    finally:
        await eng.dispose()


def test_no_global_session_object() -> None:
    import sightstalker.persistence.database as db

    assert not hasattr(db, "session")
    assert not hasattr(db, "SESSION")
    assert not hasattr(db, "global_session")


async def test_separate_calls_create_separate_sessions(engine: AsyncEngine) -> None:
    factory = create_async_session_factory(engine)
    async with database_session(factory) as s1:
        async with database_session(factory) as s2:
            assert s1 is not s2


def test_base_metadata_has_all_tables() -> None:
    names = set(Base.metadata.tables.keys())
    assert {
        "profiles",
        "sessions",
        "runs",
        "browser_contexts",
        "artifacts",
        "health_records",
    } <= names


@pytest.mark.parametrize("bad", ["", "not a url at all"])
def test_sanitize_never_raises(bad: str) -> None:
    # Sanitizer must be robust and never leak/raise.
    out = sanitize_database_url(bad)
    assert isinstance(out, str)
