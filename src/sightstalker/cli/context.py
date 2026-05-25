"""
sightstalker.cli.context — per-invocation persistence/session lifecycle.

Each async CLI command builds exactly one SQLAlchemy async engine and session
factory for the duration of one ``asyncio.run`` and disposes the engine on
exit. Transaction boundaries are owned by the command (``async with
session.begin(): ...``); repositories only flush.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.persistence import (
    AsyncSessionFactory,
    PersistenceConfig,
    create_async_engine,
    create_async_session_factory,
)


@asynccontextmanager
async def cli_persistence(
    config: CliRuntimeConfig,
) -> AsyncGenerator[AsyncSessionFactory]:
    """Yield a session factory bound to a fresh engine; dispose on exit."""
    persistence_config = PersistenceConfig(
        database_url=config.database_url,
        data_dir=config.data_dir,
    )
    engine = create_async_engine(persistence_config)
    try:
        yield create_async_session_factory(engine)
    finally:
        await engine.dispose()


__all__ = ["cli_persistence"]
