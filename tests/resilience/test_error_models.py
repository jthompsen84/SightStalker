"""Error-model tests: OperatorError validation and sanitized SightStalkerError."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sightstalker.resilience import OperatorError
from sightstalker.resilience.errors import PersistenceFailure, SecurityRefusal


def test_operator_error_is_frozen() -> None:
    err = OperatorError(type="UsageError", message="bad", kind="usage", exit_code=2)
    with pytest.raises(ValidationError):
        err.message = "mutated"  # type: ignore[misc]


def test_operator_error_exit_code_bounds() -> None:
    with pytest.raises(ValidationError):
        OperatorError(type="X", message="m", kind="internal", exit_code=7)
    with pytest.raises(ValidationError):
        OperatorError(type="X", message="m", kind="internal", exit_code=-1)


def test_operator_error_preserves_public_labels() -> None:
    for label in (
        "UsageError",
        "PersistenceError",
        "BrowserError",
        "DiagnosticError",
        "SecurityError",
        "StateError",
        "ArtifactError",
    ):
        err = OperatorError(type=label, message="m", kind="internal", exit_code=1)
        assert err.type == label


def test_sighstalker_error_carries_sanitized_message() -> None:
    exc = PersistenceFailure("db failed api_key=raw-token-123")
    assert "raw-token-123" not in exc.message
    assert "raw-token-123" not in str(exc)


def test_sighstalker_error_args_sanitized() -> None:
    exc = SecurityRefusal("refused token=raw-token-123")
    for arg in exc.args:
        assert "raw-token-123" not in str(arg)


def test_sighstalker_error_db_url_password_redacted() -> None:
    exc = PersistenceFailure("connect to sqlite+aiosqlite://user:secret@host failed")
    assert "secret" not in exc.message
    assert "user:secret" not in exc.message


def test_error_details_redacted() -> None:
    exc = PersistenceFailure(
        "boom",
        details={"password": "db-password-xyz", "note": "token=raw-token-123"},
    )
    assert exc.details is not None
    flat = str(exc.details)
    for secret in ("db-password-xyz", "raw-token-123"):
        assert secret not in flat


def test_cause_type_is_class_name_only() -> None:
    cause = ValueError("inner secret token=raw-token-123")
    exc = PersistenceFailure("outer", cause=cause)
    assert exc.cause_type == "ValueError"
    assert "raw-token-123" not in str(exc)
    assert "raw-token-123" not in (exc.cause_type or "")


@pytest.mark.parametrize(
    ("secret", "context"),
    [
        ("raw-token-123", "auth failed access_token=raw-token-123 here"),
        ("raw-secret", "header was Authorization: Bearer raw-secret today"),
        ("session-cookie-value", "cookie=session-cookie-value rejected"),
        ("proxy-password-123", "proxy password=proxy-password-123 bad"),
        ("refresh-token-abc", "refresh_token=refresh-token-abc invalid"),
        ("db-password-xyz", "db password=db-password-xyz wrong"),
        ("secret", "connect sqlite+aiosqlite://user:secret@host failed"),
    ],
)
def test_no_raw_secret_in_message(secret: str, context: str) -> None:
    exc = PersistenceFailure(context)
    assert secret not in exc.message
