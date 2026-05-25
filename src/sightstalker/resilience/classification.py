"""
sightstalker.resilience.classification — exception → OperatorError mapping.

``classify_exception`` is the single source of truth for turning any exception
into a sanitized, exit-coded :class:`OperatorError`. It reproduces the shipped
``cli/errors.py:_classify_service_exception`` behavior exactly, including:

- most-specific-first ordering (``PersistenceSecurityError`` → ``SecurityError``
  / exit 6 *before* generic ``PersistenceError`` → exit 3);
- ``SessionLifecycleError`` → ``BrowserError`` / exit 4;
- ``SessionStateError`` → ``StateError`` / exit 1;
- ``ArtifactError`` → ``ArtifactError`` / exit 1;
- ``DiagnosticError`` → ``DiagnosticError`` / exit 5;
- raw ``SQLAlchemyError`` → ``PersistenceError`` / exit 3;
- missing-schema persistence errors carry ``db init`` guidance.

``KeyboardInterrupt`` and ``SystemExit`` are re-raised unchanged — never
classified or wrapped.

Layer exception classes and ``sqlalchemy.exc`` are imported lazily *inside*
classification paths only, so importing this module never loads SQLAlchemy and
never creates an engine/session or touches a DB URL.
"""

from __future__ import annotations

from sightstalker.models import JsonObject
from sightstalker.resilience.errors import SightStalkerError
from sightstalker.resilience.models import (
    ErrorKind,
    ErrorSeverity,
    OperatorError,
    Recoverability,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_operator_details,
    sanitize_operator_message,
)

# Guidance reused when the metadata schema is missing / unreadable. Kept
# byte-compatible with the accepted ``cli/errors.py:DB_NOT_READY_GUIDANCE``.
DB_NOT_READY_GUIDANCE = (
    "database is not initialized or is unavailable; "
    "run 'sightstalker db init' first"
)


def operator_error_from_message(
    *,
    message: str,
    kind: ErrorKind,
    exit_code: int,
    severity: ErrorSeverity = "error",
    recoverability: Recoverability = "unknown",
    type: str | None = None,  # noqa: A002 - matches public spec field name
    code: str | None = None,
    details: JsonObject | None = None,
) -> OperatorError:
    """Build a sanitized :class:`OperatorError` directly from fields.

    The message and details are always sanitized; ``exit_code`` is constrained
    to ``0..6`` by the model. ``type`` defaults to a label derived from the
    kind when not supplied.
    """
    resolved_type = type if type is not None else _default_type_for_kind(kind)
    return OperatorError(
        type=resolved_type,
        message=sanitize_operator_message(message),
        kind=kind,
        severity=severity,
        recoverability=recoverability,
        exit_code=exit_code,
        code=code,
        details=sanitize_operator_details(details),
    )


def classify_exception(
    exc: BaseException,
    *,
    operation_kind: str | None = None,
    operation_name: str | None = None,
) -> OperatorError:
    """Classify ``exc`` into a sanitized :class:`OperatorError`.

    ``KeyboardInterrupt`` / ``SystemExit`` are re-raised unchanged.
    """
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise exc

    # 1) Native resilience errors carry their own taxonomy.
    if isinstance(exc, SightStalkerError):
        return OperatorError(
            type=exc.public_type,
            message=exc.message,
            kind=exc.kind,
            severity=exc.severity,
            recoverability=exc.recoverability,
            exit_code=exc.exit_code,
            code=exc.code,
            details=exc.details,
        )

    # 2) Accepted CLI errors (preserve their stable label + exit code).
    operator = _classify_cli_error(exc)
    if operator is not None:
        return operator

    # 3) Accepted service-layer exceptions (lazy imports, most-specific-first).
    operator = _classify_service_exception(exc)
    if operator is not None:
        return operator

    # 4) Unknown / unexpected → internal bug.
    return OperatorError(
        type="InternalError",
        message=sanitize_operator_message(str(exc)),
        kind="internal",
        severity="error",
        recoverability="bug",
        exit_code=1,
    )


def _default_type_for_kind(kind: ErrorKind) -> str:
    return {
        "usage": "UsageError",
        "configuration": "UsageError",
        "security_refusal": "SecurityError",
        "browser_runtime": "BrowserError",
        "persistence": "PersistenceError",
        "artifact": "ArtifactError",
        "diagnostic": "DiagnosticError",
        "timeout": "InternalError",
        "integrity": "StateError",
        "external": "Error",
        "internal": "InternalError",
    }.get(kind, "Error")


def _classify_cli_error(exc: BaseException) -> OperatorError | None:
    """Map an accepted ``cli.errors.CliError`` to an OperatorError.

    Imported lazily; the CLI delegates to resilience, and resilience tolerates
    the CLI package being absent (e.g. in pure-library contexts).
    """
    try:
        from sightstalker.cli.errors import CliError
    except Exception:  # pragma: no cover - CLI always importable in practice
        return None

    if not isinstance(exc, CliError):
        return None

    kind = _kind_for_cli_label(exc.error_type)
    return OperatorError(
        type=exc.error_type,
        message=sanitize_operator_message(exc.message),
        kind=kind,
        severity="error",
        recoverability=_recoverability_for_kind(kind),
        exit_code=exc.exit_code,
    )


def _kind_for_cli_label(label: str) -> ErrorKind:
    mapping: dict[str, ErrorKind] = {
        "UsageError": "usage",
        "PersistenceError": "persistence",
        "BrowserError": "browser_runtime",
        "DiagnosticError": "diagnostic",
        "SecurityError": "security_refusal",
        "StateError": "integrity",
        "ArtifactError": "artifact",
    }
    return mapping.get(label, "internal")


def _recoverability_for_kind(kind: ErrorKind) -> Recoverability:
    if kind in ("usage", "configuration", "browser_runtime", "persistence"):
        return "user_action_required"
    if kind == "security_refusal":
        return "do_not_retry"
    return "unknown"


def _classify_service_exception(exc: BaseException) -> OperatorError | None:
    """Reproduce ``cli/errors.py:_classify_service_exception`` exactly."""
    # Persistence (most-specific-first: security before generic).
    try:
        from sightstalker.persistence.errors import (
            PersistenceError,
            PersistenceSecurityError,
        )

        if isinstance(exc, PersistenceSecurityError):
            return OperatorError(
                type="SecurityError",
                message=sanitize_operator_message(str(exc)),
                kind="security_refusal",
                recoverability="do_not_retry",
                exit_code=6,
            )
        if isinstance(exc, PersistenceError):
            if _looks_like_missing_schema(exc):
                return OperatorError(
                    type="PersistenceError",
                    message=DB_NOT_READY_GUIDANCE,
                    kind="persistence",
                    recoverability="user_action_required",
                    exit_code=3,
                    code="PERSISTENCE_NOT_INITIALIZED",
                )
            return OperatorError(
                type="PersistenceError",
                message=sanitize_operator_message(str(exc)),
                kind="persistence",
                recoverability="user_action_required",
                exit_code=3,
            )
    except ImportError:  # pragma: no cover - persistence always importable
        pass

    # Diagnostics.
    try:
        from sightstalker.diagnostics.errors import DiagnosticError

        if isinstance(exc, DiagnosticError):
            return OperatorError(
                type="DiagnosticError",
                message=sanitize_operator_message(str(exc)),
                kind="diagnostic",
                recoverability="unknown",
                exit_code=5,
            )
    except ImportError:  # pragma: no cover
        pass

    # Sessions.
    try:
        from sightstalker.sessions.errors import (
            SessionLifecycleError,
            SessionStateError,
        )

        if isinstance(exc, SessionLifecycleError):
            return OperatorError(
                type="BrowserError",
                message=sanitize_operator_message(str(exc)),
                kind="browser_runtime",
                recoverability="unknown",
                exit_code=4,
            )
        if isinstance(exc, SessionStateError):
            return OperatorError(
                type="StateError",
                message=sanitize_operator_message(str(exc)),
                kind="integrity",
                recoverability="unknown",
                exit_code=1,
            )
    except ImportError:  # pragma: no cover
        pass

    # Artifacts.
    try:
        from sightstalker.artifacts.errors import ArtifactError

        if isinstance(exc, ArtifactError):
            return OperatorError(
                type="ArtifactError",
                message=sanitize_operator_message(str(exc)),
                kind="artifact",
                recoverability="unknown",
                exit_code=1,
            )
    except ImportError:  # pragma: no cover
        pass

    # Raw SQLAlchemy errors → persistence (missing-schema gets guidance).
    operator = _classify_sqlalchemy_error(exc)
    if operator is not None:
        return operator

    return None


def _classify_sqlalchemy_error(exc: BaseException) -> OperatorError | None:
    """Lazily classify a raw SQLAlchemy error as a persistence failure.

    ``sqlalchemy.exc`` is imported only here, inside the classification path.
    No engine/session is created and no DB URL is handled.
    """
    try:
        from sqlalchemy.exc import SQLAlchemyError
    except ImportError:  # pragma: no cover
        return None

    if not isinstance(exc, SQLAlchemyError):
        return None

    if _looks_like_missing_schema(exc):
        return OperatorError(
            type="PersistenceError",
            message=DB_NOT_READY_GUIDANCE,
            kind="persistence",
            recoverability="user_action_required",
            exit_code=3,
            code="PERSISTENCE_NOT_INITIALIZED",
        )
    return OperatorError(
        type="PersistenceError",
        message=sanitize_operator_message(str(exc)),
        kind="persistence",
        recoverability="user_action_required",
        exit_code=3,
    )


def _looks_like_missing_schema(exc: BaseException) -> bool:
    """Heuristic: a SQLAlchemy operational error about a missing table/db."""
    try:
        from sqlalchemy.exc import OperationalError
    except ImportError:  # pragma: no cover
        return False

    if isinstance(exc, OperationalError):
        text = str(exc).lower()
        return (
            "no such table" in text
            or "does not exist" in text
            or "unable to open database" in text
        )
    return False


# Deprecated compatibility alias — routes to the sanitized implementation.
def classify_message(
    *,
    message: str,
    kind: ErrorKind,
    exit_code: int,
    severity: ErrorSeverity = "error",
    recoverability: Recoverability = "unknown",
    type: str | None = None,  # noqa: A002
    code: str | None = None,
    details: JsonObject | None = None,
) -> OperatorError:
    """Deprecated alias for :func:`operator_error_from_message`."""
    return operator_error_from_message(
        message=message,
        kind=kind,
        exit_code=exit_code,
        severity=severity,
        recoverability=recoverability,
        type=type,
        code=code,
        details=details,
    )


__all__ = [
    "DB_NOT_READY_GUIDANCE",
    "classify_exception",
    "classify_message",
    "operator_error_from_message",
]
