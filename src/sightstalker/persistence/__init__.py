"""Async SQL metadata persistence for SightStalker.

Stores only sanitized metadata and ``ArtifactRef``-style provenance for
profiles, sessions, runs, browser contexts, artifacts, and health records. Raw
browser state, cookies, screenshots, traces, and artifact payloads remain in
the filesystem artifact layer and must never be stored in SQL.

Importing this package pulls in SQLAlchemy and Alembic; importing the rest of
``sightstalker`` does not.
"""

from sightstalker.persistence.alembic import make_alembic_config
from sightstalker.persistence.database import (
    AsyncSessionFactory,
    PersistenceConfig,
    create_async_engine,
    create_async_session_factory,
    database_session,
    sanitize_database_url,
)
from sightstalker.persistence.errors import (
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
    PersistenceSecurityError,
)
from sightstalker.persistence.repositories import (
    ArtifactRepository,
    BrowserContextRepository,
    HealthRepository,
    ProfileRepository,
    RunRepository,
    SessionRepository,
)

__all__ = [
    "ArtifactRepository",
    "AsyncSessionFactory",
    "BrowserContextRepository",
    "HealthRepository",
    "PersistenceConfig",
    "PersistenceError",
    "PersistenceIntegrityError",
    "PersistenceNotFoundError",
    "PersistenceSecurityError",
    "ProfileRepository",
    "RunRepository",
    "SessionRepository",
    "create_async_engine",
    "create_async_session_factory",
    "database_session",
    "make_alembic_config",
    "sanitize_database_url",
]
