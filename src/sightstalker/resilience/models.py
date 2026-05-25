"""
sightstalker.resilience.models — taxonomy literals and operator-facing models.

These are pure Pydantic/typing contracts: importing this module must not pull
in tenacity, loguru, SQLAlchemy, Typer, Rich, or any browser package.

``OperatorError`` is the single machine-facing failure object. Its ``type``
field preserves the stable v0.4.0 CLI labels (``UsageError``,
``PersistenceError``, ``BrowserError``, ``DiagnosticError``, ``SecurityError``,
``StateError``, ``ArtifactError``); the project taxonomy is expressed through
``kind`` / ``severity`` / ``recoverability`` and the optional fine-grained
``code``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from sightstalker.models import JsonObject, ToolkitModel

ErrorKind = Literal[
    "usage",
    "configuration",
    "security_refusal",
    "browser_runtime",
    "persistence",
    "artifact",
    "diagnostic",
    "timeout",
    "integrity",
    "external",
    "internal",
]

ErrorSeverity = Literal["info", "warning", "error", "critical"]

Recoverability = Literal[
    "user_action_required",
    "safe_to_retry",
    "do_not_retry",
    "bug",
    "unknown",
]


class OperatorError(ToolkitModel):
    """Immutable, machine-facing description of a handled failure.

    ``type`` is the stable public label (backward compatible with v0.4.0 CLI
    output). The taxonomy fields are additive. ``exit_code`` is constrained to
    the accepted process exit-code range ``0..6``.
    """

    type: str
    message: str
    kind: ErrorKind
    severity: ErrorSeverity = "error"
    recoverability: Recoverability = "unknown"
    exit_code: int = Field(ge=0, le=6)
    code: str | None = None
    details: JsonObject | None = None


class ResiliencePolicy(ToolkitModel):
    """Controls how much detail operator formatting/logging may include.

    Defaults are conservative: no debug details, never tracebacks, always
    redact. ``include_tracebacks`` exists only for future compatibility and
    must not be enabled by any CLI/default path in this release.
    """

    include_debug_details: bool = False
    include_tracebacks: bool = False
    redact_messages: bool = True


__all__ = [
    "ErrorKind",
    "ErrorSeverity",
    "OperatorError",
    "Recoverability",
    "ResiliencePolicy",
]
