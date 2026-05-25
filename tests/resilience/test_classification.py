"""Classification tests: exact equivalence with the accepted CLI classifier."""

from __future__ import annotations

import pytest

from sightstalker.artifacts.errors import ArtifactError
from sightstalker.cli.errors import (
    CliBrowserError,
    CliPersistenceError,
    CliSecurityError,
    CliUsageError,
)
from sightstalker.diagnostics.errors import DiagnosticError
from sightstalker.persistence.errors import (
    PersistenceError,
    PersistenceSecurityError,
)
from sightstalker.resilience import classify_exception, operator_error_from_message
from sightstalker.resilience.classification import DB_NOT_READY_GUIDANCE
from sightstalker.sessions.errors import SessionLifecycleError, SessionStateError


def test_usage_error_maps_to_usage_exit_2() -> None:
    oe = classify_exception(CliUsageError("bad input"))
    assert oe.type == "UsageError"
    assert oe.kind == "usage"
    assert oe.exit_code == 2


def test_security_refusal_maps_to_security_exit_6() -> None:
    oe = classify_exception(CliSecurityError("refused"))
    assert oe.type == "SecurityError"
    assert oe.kind == "security_refusal"
    assert oe.exit_code == 6


def test_persistence_security_before_generic_persistence() -> None:
    # PersistenceSecurityError is a subclass of PersistenceError; it must map to
    # SecurityError/6, not PersistenceError/3.
    oe = classify_exception(PersistenceSecurityError("must not persist"))
    assert oe.type == "SecurityError"
    assert oe.kind == "security_refusal"
    assert oe.exit_code == 6


def test_browser_runtime_error_maps_to_browser_exit_4() -> None:
    oe = classify_exception(CliBrowserError("no browser"))
    assert oe.type == "BrowserError"
    assert oe.kind == "browser_runtime"
    assert oe.exit_code == 4


def test_persistence_error_maps_to_persistence_exit_3() -> None:
    oe = classify_exception(CliPersistenceError("db down"))
    assert oe.type == "PersistenceError"
    assert oe.kind == "persistence"
    assert oe.exit_code == 3


def test_raw_persistence_error_maps_to_persistence() -> None:
    oe = classify_exception(PersistenceError("connection lost"))
    assert oe.type == "PersistenceError"
    assert oe.exit_code == 3


def test_missing_schema_includes_db_init_guidance() -> None:
    from sqlalchemy.exc import OperationalError

    exc = OperationalError("SELECT 1", {}, Exception("no such table: runs"))
    oe = classify_exception(exc)
    assert oe.type == "PersistenceError"
    assert oe.exit_code == 3
    assert "db init" in oe.message
    assert oe.message == DB_NOT_READY_GUIDANCE
    assert oe.code == "PERSISTENCE_NOT_INITIALIZED"


def test_raw_sqlalchemy_error_maps_to_persistence_exit_3() -> None:
    from sqlalchemy.exc import IntegrityError

    exc = IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed"))
    oe = classify_exception(exc)
    assert oe.type == "PersistenceError"
    assert oe.exit_code == 3


def test_diagnostic_error_maps_to_diagnostic_exit_5() -> None:
    oe = classify_exception(DiagnosticError("snap failed"))
    assert oe.type == "DiagnosticError"
    assert oe.kind == "diagnostic"
    assert oe.exit_code == 5


def test_artifact_error_maps_to_artifact_exit_1() -> None:
    oe = classify_exception(ArtifactError("write failed"))
    assert oe.type == "ArtifactError"
    assert oe.kind == "artifact"
    assert oe.exit_code == 1


def test_session_state_error_maps_to_state_exit_1() -> None:
    oe = classify_exception(SessionStateError("corrupt state"))
    assert oe.type == "StateError"
    assert oe.kind == "integrity"
    assert oe.exit_code == 1


def test_session_lifecycle_error_maps_to_browser_exit_4() -> None:
    oe = classify_exception(SessionLifecycleError("lifecycle blew up"))
    assert oe.type == "BrowserError"
    assert oe.kind == "browser_runtime"
    assert oe.exit_code == 4


def test_contextless_timeout_is_conservative() -> None:
    oe = classify_exception(TimeoutError("timed out"))
    # A bare timeout maps to internal/bug (unexpected) unless richer context is
    # provided; it must never be auto-classified as safe_to_retry.
    assert oe.recoverability != "safe_to_retry"


def test_unexpected_error_maps_to_internal_bug() -> None:
    oe = classify_exception(ValueError("surprise"))
    assert oe.type == "InternalError"
    assert oe.kind == "internal"
    assert oe.recoverability == "bug"
    assert oe.exit_code == 1


def test_keyboard_interrupt_reraises() -> None:
    with pytest.raises(KeyboardInterrupt):
        classify_exception(KeyboardInterrupt())


def test_system_exit_reraises() -> None:
    with pytest.raises(SystemExit):
        classify_exception(SystemExit(3))


def test_raw_secrets_absent_from_classified_fields() -> None:
    exc = PersistenceError(
        "auth failed access_token=raw-token-123 at "
        "sqlite+aiosqlite://user:secret@host"
    )
    oe = classify_exception(exc)
    blob = (
        f"{oe.type}{oe.message}{oe.kind}{oe.recoverability}"
        f"{oe.code}{oe.details}"
    )
    for secret in ("raw-token-123", "user:secret", "secret@host"):
        assert secret not in blob


def test_operator_error_from_message_sanitizes_and_bounds_exit() -> None:
    oe = operator_error_from_message(
        message="boom token=raw-token-123",
        kind="persistence",
        exit_code=3,
    )
    assert "raw-token-123" not in oe.message
    assert oe.type == "PersistenceError"
    assert oe.exit_code == 3
