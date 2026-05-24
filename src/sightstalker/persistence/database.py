"""
sightstalker.persistence.database — async SQLAlchemy engine/session helpers.

Provides the ``PersistenceConfig`` settings object, async engine and session
factory constructors, a session context manager, and a database-URL sanitizer.

Transaction discipline is the caller's responsibility: ``database_session``
opens and closes a session but never commits. Repositories flush, never commit.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeAlias
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine as _sa_create_async_engine,
)

from sightstalker.models import ToolkitModel

AsyncSessionFactory: TypeAlias = async_sessionmaker[AsyncSession]


class PersistenceConfig(ToolkitModel):
    """Configuration for the persistence layer.

    ``database_url`` is excluded from repr to avoid leaking credentials. The
    ``data_dir`` is the trusted root used to normalize/contain profile paths.
    """

    database_url: str = Field(repr=False)
    data_dir: Path
    echo: bool = False


def sanitize_database_url(url: str) -> str:
    """Return ``url`` with any userinfo (user:password) removed.

    Returns the URL unchanged when no credentials are present (avoiding
    round-trip normalization quirks for URLs like ``sqlite+aiosqlite:///x``).
    Falls back to a placeholder if the URL cannot be parsed. Never raises and
    never returns embedded credentials.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable-database-url>"
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    sanitized = parts._replace(netloc=host)
    return urlunsplit(sanitized)


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_async_engine(config: PersistenceConfig) -> AsyncEngine:
    """Create an ``AsyncEngine`` from ``config``.

    For SQLite URLs, foreign-key enforcement is enabled on every pooled DBAPI
    connection through a ``connect`` event hook.
    """
    engine = _sa_create_async_engine(config.database_url, echo=config.echo)

    if _is_sqlite(config.database_url):

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(  # pyright: ignore[reportUnusedFunction]
            dbapi_connection: Any, connection_record: Any
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_async_session_factory(engine: AsyncEngine) -> AsyncSessionFactory:
    """Create an ``async_sessionmaker`` bound to ``engine``."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def database_session(
    factory: AsyncSessionFactory,
) -> AsyncGenerator[AsyncSession]:
    """Open a new ``AsyncSession``, yield it, and close it on exit.

    Does not commit and does not swallow exceptions; the caller owns the
    transaction boundary (typically ``async with session.begin(): ...``).
    """
    session = factory()
    try:
        yield session
    finally:
        await session.close()
