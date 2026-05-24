"""
sightstalker.persistence.errors — persistence-layer exception hierarchy.

All persistence errors are sanitized: messages must never include raw SQL
statements, database URLs with credentials, absolute filesystem paths, cookies,
storage state, headers, tokens, proxy credentials, or environment values.
"""

from __future__ import annotations


class PersistenceError(RuntimeError):
    """Base class for persistence-layer failures."""


class PersistenceIntegrityError(PersistenceError):
    """Raised for unique, foreign-key, validation, and database-integrity failures."""


class PersistenceNotFoundError(PersistenceError):
    """Raised when a requested persisted record is absent."""


class PersistenceSecurityError(PersistenceError):
    """Raised when a record contains data that must not be persisted."""
