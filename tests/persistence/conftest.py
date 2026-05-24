"""Shared fixtures for persistence tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sightstalker.persistence.database import (
    PersistenceConfig,
    create_async_engine,
    create_async_session_factory,
)
from sightstalker.persistence.models import Base


def make_config(data_dir: Path) -> PersistenceConfig:
    return PersistenceConfig(
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=data_dir,
    )


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    config = make_config(tmp_path / "data")
    eng = create_async_engine(config)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = create_async_session_factory(engine)
    async with factory() as s:
        yield s
