"""
sightstalker.resilience.errors — project-wide sanitized exception taxonomy.

``SightStalkerError`` is the root of the resilience taxonomy. Its initializer
sanitizes the message *before* calling ``RuntimeError.__init__`` so that
``str(exc)``, ``exc.args``, and ``exc.message`` can never carry raw tokens, DB
URL credentials, ``data:`` bodies, or query/fragment secrets.

Cause handling is deliberately minimal: only the *class name* of a cause is
retained (``cause_type``). Raw ``repr(cause)`` / ``str(cause)`` text, chained
messages, tracebacks, and locals are never stored or rendered.

Existing layer exceptions (ArtifactError, PersistenceError, DiagnosticError,
SessionStateError, ...) are NOT forced to subclass this hierarchy; the
classifier maps them to ``OperatorError`` instead.
"""

from __future__ import annotations

from sightstalker.models import JsonObject
from sightstalker.resilience.models import (
    ErrorKind,
    ErrorSeverity,
    Recoverability,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_operator_details,
    sanitize_operator_message,
)


class SightStalkerError(RuntimeError):
    """Base of the sanitized project error taxonomy.

    Subclasses set class-level ``kind`` / ``severity`` / ``recoverability`` /
    ``exit_code`` / ``public_type`` defaults; any of these may be overridden
    per-instance via constructor keywords.
    """

    kind: ErrorKind = "internal"
    severity: ErrorSeverity = "error"
    recoverability: Recoverability = "unknown"
    exit_code: int = 1
    public_type: str = "InternalError"

    def __init__(
        self,
        message: str,
        *,
        kind: ErrorKind | None = None,
        severity: ErrorSeverity | None = None,
        recoverability: Recoverability | None = None,
        exit_code: int | None = None,
        public_type: str | None = None,
        code: str | None = None,
        cause: BaseException | None = None,
        details: JsonObject | None = None,
    ) -> None:
        safe_message = sanitize_operator_message(message)
        # Sanitize BEFORE RuntimeError.__init__ so .args/str(self) are safe.
        super().__init__(safe_message)
        self.message: str = safe_message
        self.kind = kind if kind is not None else type(self).kind
        self.severity = severity if severity is not None else type(self).severity
        self.recoverability = (
            recoverability
            if recoverability is not None
            else type(self).recoverability
        )
        self.exit_code = exit_code if exit_code is not None else type(self).exit_code
        self.public_type = (
            public_type if public_type is not None else type(self).public_type
        )
        self.code: str | None = code
        self.cause_type: str | None = (
            cause.__class__.__name__ if cause is not None else None
        )
        self.details: JsonObject | None = sanitize_operator_details(details)


class ResilienceError(SightStalkerError):
    """Failure originating inside the resilience layer itself."""

    kind = "internal"
    public_type = "InternalError"
    exit_code = 1


class UsageError(SightStalkerError):
    """Invalid operator input / configuration usage (exit 2)."""

    kind = "usage"
    recoverability = "user_action_required"
    exit_code = 2
    public_type = "UsageError"


class ConfigurationError(SightStalkerError):
    """Invalid or unsafe configuration (exit 2)."""

    kind = "configuration"
    recoverability = "user_action_required"
    exit_code = 2
    public_type = "UsageError"


class SecurityRefusal(SightStalkerError):
    """Refusal to act on unsafe input/configuration (exit 6)."""

    kind = "security_refusal"
    recoverability = "do_not_retry"
    exit_code = 6
    public_type = "SecurityError"


class BrowserRuntimeError(SightStalkerError):
    """Browser runtime unavailable / failed to launch (exit 4)."""

    kind = "browser_runtime"
    recoverability = "user_action_required"
    exit_code = 4
    public_type = "BrowserError"


class PersistenceFailure(SightStalkerError):
    """Database / persistence failure (exit 3)."""

    kind = "persistence"
    recoverability = "user_action_required"
    exit_code = 3
    public_type = "PersistenceError"


class DiagnosticFailure(SightStalkerError):
    """Diagnostic capture / persistence failure (exit 5)."""

    kind = "diagnostic"
    recoverability = "unknown"
    exit_code = 5
    public_type = "DiagnosticError"


class TimeoutFailure(SightStalkerError):
    """A bounded operation exceeded its time budget.

    Recoverability is conservative (``unknown``) unless a caller supplies more
    context; this is not, by itself, a signal to retry.
    """

    kind = "timeout"
    recoverability = "unknown"
    exit_code = 1
    public_type = "InternalError"


__all__ = [
    "BrowserRuntimeError",
    "ConfigurationError",
    "DiagnosticFailure",
    "PersistenceFailure",
    "ResilienceError",
    "SecurityRefusal",
    "SightStalkerError",
    "TimeoutFailure",
    "UsageError",
]
