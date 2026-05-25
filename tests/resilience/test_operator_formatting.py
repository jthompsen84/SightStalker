"""Operator-formatting tests: JSON/human shapes and sanitization."""

from __future__ import annotations

from sightstalker.persistence.errors import PersistenceError
from sightstalker.resilience import OperatorError
from sightstalker.resilience.errors import PersistenceFailure
from sightstalker.resilience.operator import (
    error_to_operator_error,
    exception_to_operator_error,
    operator_error_to_human,
    operator_error_to_json,
)


def _err(**kw: object) -> OperatorError:
    base: dict[str, object] = {
        "type": "PersistenceError",
        "message": "m",
        "kind": "persistence",
        "exit_code": 3,
    }
    base.update(kw)
    return OperatorError(**base)  # type: ignore[arg-type]


def test_human_format_is_sanitized() -> None:
    oe = exception_to_operator_error(
        PersistenceError("boom access_token=raw-token-123")
    )
    human = operator_error_to_human(oe)
    assert "raw-token-123" not in human


def test_json_includes_taxonomy_fields() -> None:
    oe = _err(recoverability="user_action_required", severity="error")
    payload = operator_error_to_json(oe)
    for field in (
        "type",
        "message",
        "kind",
        "severity",
        "recoverability",
        "exit_code",
    ):
        assert field in payload
    assert payload["type"] == "PersistenceError"
    assert payload["kind"] == "persistence"
    assert payload["exit_code"] == 3


def test_json_details_default_is_empty_object() -> None:
    payload = operator_error_to_json(_err())
    assert payload["details"] == {}


def test_no_traceback_in_human_or_json() -> None:
    oe = exception_to_operator_error(ValueError("kaboom"))
    human = operator_error_to_human(oe)
    payload = operator_error_to_json(oe)
    assert "Traceback" not in human
    assert "Traceback" not in str(payload)


def test_details_sanitized() -> None:
    oe = _err(details={"password": "db-password-xyz", "ok": "fine"})
    payload = operator_error_to_json(oe)
    assert "db-password-xyz" not in str(payload)


def test_db_url_redacted_in_message() -> None:
    oe = exception_to_operator_error(
        PersistenceError("connect sqlite+aiosqlite://user:secret@host failed")
    )
    payload = operator_error_to_json(oe)
    assert "secret" not in str(payload)


def test_optional_code_serializes_when_supplied() -> None:
    oe = _err(code="PERSISTENCE_NOT_INITIALIZED")
    payload = operator_error_to_json(oe)
    assert payload["code"] == "PERSISTENCE_NOT_INITIALIZED"


def test_code_is_none_when_absent() -> None:
    payload = operator_error_to_json(_err())
    assert payload["code"] is None


def test_error_to_operator_error_preserves_taxonomy() -> None:
    err = PersistenceFailure("db failed", code="PERSISTENCE_NOT_INITIALIZED")
    oe = error_to_operator_error(err)
    assert oe.type == "PersistenceError"
    assert oe.kind == "persistence"
    assert oe.exit_code == 3
    assert oe.code == "PERSISTENCE_NOT_INITIALIZED"


def test_human_recoverability_hint() -> None:
    oe = _err(recoverability="user_action_required")
    assert "action required" in operator_error_to_human(oe)
