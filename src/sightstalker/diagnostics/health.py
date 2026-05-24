"""
sightstalker.diagnostics.health — passive health record service.

Builds ``SessionHealthRecord`` value objects (with sanitized reasons) and
optionally persists them through an injected repository-like protocol. It never
runs browser health probes or network checks, and never commits DB sessions.
"""

from __future__ import annotations

from typing import Protocol

from sightstalker.diagnostics.errors import DiagnosticPersistenceError
from sightstalker.models import (
    HealthStatus,
    RunId,
    SessionHealthRecord,
    SessionId,
)
from sightstalker.security.redaction import redact_string


class HealthPersistenceProtocol(Protocol):
    """Repository-like health record sink (no SQLAlchemy import)."""

    async def create(
        self, record: SessionHealthRecord
    ) -> SessionHealthRecord: ...


class HealthService:
    """Builds and optionally persists session health records."""

    def __init__(
        self, *, health_persistence: HealthPersistenceProtocol | None = None
    ) -> None:
        self._persistence = health_persistence

    def build_record(
        self,
        *,
        session_id: SessionId,
        status: HealthStatus,
        reason: str | None = None,
        last_successful_run_id: RunId | None = None,
        last_failed_run_id: RunId | None = None,
    ) -> SessionHealthRecord:
        """Build a ``SessionHealthRecord`` with a sanitized reason."""
        sanitized_reason = redact_string(reason) if reason is not None else None
        return SessionHealthRecord(
            session_id=session_id,
            status=status,
            reason=sanitized_reason,
            last_successful_run_id=last_successful_run_id,
            last_failed_run_id=last_failed_run_id,
        )

    async def persist_record(
        self, record: SessionHealthRecord
    ) -> SessionHealthRecord:
        """Persist a health record through the injected repository.

        Does not commit. Raises ``DiagnosticPersistenceError`` if no repository
        was provided or the repository call fails.
        """
        if self._persistence is None:
            raise DiagnosticPersistenceError(
                "health persistence requested but no repository was provided"
            )
        # Re-sanitize defensively in case a raw record was passed directly.
        safe = record
        if record.reason is not None:
            safe = record.model_copy(
                update={"reason": redact_string(record.reason)}
            )
        try:
            return await self._persistence.create(safe)
        except Exception as exc:
            raise DiagnosticPersistenceError(
                f"health record persistence failed: {type(exc).__name__}"
            ) from None
