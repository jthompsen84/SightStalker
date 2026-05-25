"""
sightstalker.cli.errors — CLI error taxonomy and exit-code mapping.

Every CLI error carries an already-sanitized, log-safe message and a stable
process exit code. ``map_exception`` translates both CLI errors and the
accepted service-layer exceptions (persistence, diagnostics, sessions,
artifacts, SQLAlchemy) into a ``(exit_code, error_entry, warnings)`` triple for
the central output wrapper.

Service-layer exception classes are imported lazily inside ``map_exception`` so
that importing this module (and therefore ``sightstalker.cli.main``) stays
light and never pulls SQLAlchemy or other heavy packages at CLI import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sightstalker.cli.exit_codes import (
    EXIT_BROWSER,
    EXIT_DIAGNOSTIC,
    EXIT_GENERAL_ERROR,
    EXIT_PERSISTENCE,
    EXIT_SECURITY,
    EXIT_USAGE,
)

if TYPE_CHECKING:
    from sightstalker.resilience.models import OperatorError


class CliError(Exception):
    """Base CLI error with a sanitized message, exit code, and warnings.

    The ``message`` is expected to be safe for stdout/stderr/JSON output; the
    central wrapper sanitizes again as a backstop. ``error_type`` is the stable
    label surfaced in the JSON failure envelope.
    """

    exit_code: int = EXIT_GENERAL_ERROR
    error_type: str = "CliError"

    def __init__(self, message: str, *, warnings: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.warnings: list[str] = list(warnings) if warnings else []


class CliUsageError(CliError):
    """Operator/config/input validation error (invalid id, url, limit, ...)."""

    exit_code = EXIT_USAGE
    error_type = "UsageError"


class CliPersistenceError(CliError):
    """Database/persistence failure (including uninitialized schema)."""

    exit_code = EXIT_PERSISTENCE
    error_type = "PersistenceError"


class CliBrowserError(CliError):
    """Browser runtime missing, unsupported, or failed to launch."""

    exit_code = EXIT_BROWSER
    error_type = "BrowserError"


class CliDiagnosticError(CliError):
    """Diagnostic capture failure."""

    exit_code = EXIT_DIAGNOSTIC
    error_type = "DiagnosticError"


class CliSecurityError(CliError):
    """Security/redaction refusal (unsafe URL or unsafe config)."""

    exit_code = EXIT_SECURITY
    error_type = "SecurityError"


# Guidance reused when the metadata schema is missing / unreadable.
DB_NOT_READY_GUIDANCE = (
    "database is not initialized or is unavailable; "
    "run 'sightstalker db init' first"
)


def map_exception(exc: BaseException) -> tuple[int, dict[str, str], list[str]]:
    """Map an exception to ``(exit_code, error_entry, warnings)``.

    As of v0.4.1 this delegates classification to
    ``sightstalker.resilience.classify_exception`` so the project has a single
    failure taxonomy. The returned ``error_entry`` preserves the stable
    ``{"type", "message"}`` shape (and the stable public ``type`` labels) that
    the v0.4.0 CLI output contract guarantees. ``map_exception_full`` exposes
    the richer ``OperatorError`` for the enriched JSON envelope.
    """
    code, entry, warnings, _operator = map_exception_full(exc)
    return code, entry, warnings


def map_exception_full(
    exc: BaseException,
) -> tuple[int, dict[str, str], list[str], "OperatorError"]:
    """Like :func:`map_exception` but also returns the full ``OperatorError``.

    Operator warnings are preserved from any exception that exposes a
    ``warnings`` attribute — both the CLI's ``CliError`` and ops-layer errors
    such as ``OpsPersistenceFailure`` (which carries the orphan-artifact
    warning). The resilience classifier owns label, kind, exit code, and
    sanitized message.
    """
    from sightstalker.resilience import exception_to_operator_error

    operator = exception_to_operator_error(exc)
    warnings = _extract_warnings(exc)
    entry = {"type": operator.type, "message": operator.message}
    return operator.exit_code, entry, warnings, operator


def _extract_warnings(exc: BaseException) -> list[str]:
    """Pull operator warnings off an exception regardless of its layer.

    Accepts both ``list[str]`` (CLI errors) and ``tuple[str, ...]`` (ops
    errors); ignores any non-string-sequence ``warnings`` attribute.
    """
    raw = getattr(exc, "warnings", None)
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]  # type: ignore[misc]
    return []


__all__ = [
    "CliBrowserError",
    "CliDiagnosticError",
    "CliError",
    "CliPersistenceError",
    "CliSecurityError",
    "CliUsageError",
    "DB_NOT_READY_GUIDANCE",
    "map_exception",
    "map_exception_full",
]
