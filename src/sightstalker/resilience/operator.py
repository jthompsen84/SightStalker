"""
sightstalker.resilience.operator — operator-error formatting helpers.

Thin, dependency-light wrappers used by the CLI to turn exceptions and native
``SightStalkerError`` instances into :class:`OperatorError` objects and into
the JSON / human shapes the CLI emits. No Typer / Rich imports here; the CLI
owns the actual console rendering.
"""

from __future__ import annotations

from sightstalker.models import JsonObject
from sightstalker.resilience.classification import classify_exception
from sightstalker.resilience.errors import SightStalkerError
from sightstalker.resilience.models import OperatorError


def exception_to_operator_error(exc: BaseException) -> OperatorError:
    """Classify any exception into a sanitized :class:`OperatorError`.

    ``KeyboardInterrupt`` / ``SystemExit`` propagate (via ``classify_exception``).
    """
    return classify_exception(exc)


def error_to_operator_error(error: SightStalkerError) -> OperatorError:
    """Convert a native taxonomy error into an :class:`OperatorError`."""
    return OperatorError(
        type=error.public_type,
        message=error.message,
        kind=error.kind,
        severity=error.severity,
        recoverability=error.recoverability,
        exit_code=error.exit_code,
        code=error.code,
        details=error.details,
    )


def operator_error_to_json(error: OperatorError) -> JsonObject:
    """Return the CLI-envelope-compatible JSON object for an error.

    Always includes the stable ``type`` plus the taxonomy fields. The message
    and details are re-sanitized here as a defensive output backstop (idempotent
    for already-sanitized values), so any ``OperatorError`` — however it was
    constructed — renders safely. ``details`` defaults to an empty object.
    """
    from sightstalker.resilience.operator_redaction import (
        sanitize_operator_details,
        sanitize_operator_message,
    )

    details = sanitize_operator_details(error.details)
    return {
        "type": error.type,
        "message": sanitize_operator_message(error.message),
        "kind": error.kind,
        "severity": error.severity,
        "recoverability": error.recoverability,
        "exit_code": error.exit_code,
        "code": error.code,
        "details": details if details is not None else {},
    }


def operator_error_to_human(error: OperatorError) -> str:
    """Return a concise, sanitized one-line human message (no traceback)."""
    suffix = ""
    if error.recoverability == "user_action_required":
        suffix = " (action required)"
    elif error.recoverability == "safe_to_retry":
        suffix = " (safe to retry)"
    return f"{error.message}{suffix}"


__all__ = [
    "error_to_operator_error",
    "exception_to_operator_error",
    "operator_error_to_human",
    "operator_error_to_json",
]
