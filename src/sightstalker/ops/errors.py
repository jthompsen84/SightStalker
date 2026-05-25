"""
sightstalker.ops.errors — ops-local sanitized errors that can carry warnings.

The resilience base error does not carry operator warnings, but the accepted
orphan-artifact policy must surface a warning alongside a persistence failure.
``OpsPersistenceFailure`` subclasses the resilience ``PersistenceFailure`` so it
keeps the sanitized message, the ``persistence`` kind, and the public
``PersistenceError`` label, while adding a ``warnings`` tuple that the CLI
failure path propagates into the JSON/human envelope.

No public ``OpsError`` label is introduced; these errors classify exactly like
their resilience bases.
"""

from __future__ import annotations

from sightstalker.resilience.errors import PersistenceFailure


class OpsPersistenceFailure(PersistenceFailure):
    """Persistence failure from ops orchestration that may carry warnings."""

    def __init__(self, message: str, *, warnings: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.warnings: tuple[str, ...] = warnings


__all__ = ["OpsPersistenceFailure"]
