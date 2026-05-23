"""
Redaction utility tests for FOUNDATION-CONTRACT-1.

Verifies all required redaction behaviors:
- Mapping-level key redaction (cookies, auth, proxy, password, tokens)
- Nested structure redaction
- Sequence redaction
- SecretStr / SecretBytes handling
- String-level token pattern redaction
- Exception sanitization
- loguru-compatible in-place record mutation
"""

from __future__ import annotations

from typing import Any

from pydantic import SecretBytes, SecretStr

from sightstalker.security import (
    redact_exception,
    redact_log_record,
    redact_mapping,
    redact_string,
    redact_value,
)


# ---------------------------------------------------------------------------
# redact_mapping — key-level redaction
# ---------------------------------------------------------------------------


def test_redact_mapping_redacts_cookies() -> None:
    result = redact_mapping({"cookies": [{"name": "session", "value": "abc123"}]})
    assert result["cookies"] == "<redacted>"


def test_redact_mapping_redacts_authorization() -> None:
    result = redact_mapping({"authorization": "Bearer tok_supersecret"})
    assert result["authorization"] == "<redacted>"


def test_redact_mapping_redacts_proxy_authorization() -> None:
    result = redact_mapping({"proxy-authorization": "Basic dXNlcjpwYXNz"})
    assert result["proxy-authorization"] == "<redacted>"


def test_redact_mapping_redacts_set_cookie() -> None:
    result = redact_mapping({"set-cookie": "sid=abc123; HttpOnly"})
    assert result["set-cookie"] == "<redacted>"


def test_redact_mapping_redacts_password() -> None:
    result = redact_mapping({"password": "hunter2"})
    assert result["password"] == "<redacted>"


def test_redact_mapping_redacts_passphrase() -> None:
    result = redact_mapping({"passphrase": "correct horse battery staple"})
    assert result["passphrase"] == "<redacted>"


def test_redact_mapping_redacts_access_token() -> None:
    result = redact_mapping({"access_token": "eyJhbGciOiJIUzI1NiJ9.secret"})
    assert result["access_token"] == "<redacted>"


def test_redact_mapping_redacts_api_key() -> None:
    result = redact_mapping({"api_key": "sk_live_abc123"})
    assert result["api_key"] == "<redacted>"


def test_redact_mapping_redacts_storage_state() -> None:
    result = redact_mapping({"storage_state": {"cookies": [], "origins": []}})
    assert result["storage_state"] == "<redacted>"


def test_redact_mapping_preserves_non_sensitive_keys() -> None:
    result = redact_mapping({"url": "https://example.com", "status": 200})
    assert result["url"] == "https://example.com"
    assert result["status"] == 200


def test_redact_mapping_redacts_nested_secrets() -> None:
    data = {
        "request": {
            "headers": {
                "authorization": "Bearer tok_nested",
                "content-type": "application/json",
            }
        }
    }
    result = redact_mapping(data)
    assert result["request"]["headers"]["authorization"] == "<redacted>"
    assert result["request"]["headers"]["content-type"] == "application/json"


def test_redact_mapping_redacts_secrets_inside_sequences() -> None:
    data = {
        "items": [
            {"name": "safe", "value": "ok"},
            {"password": "secret123", "user": "alice"},
        ]
    }
    result = redact_mapping(data)
    items = result["items"]
    assert isinstance(items, list)
    assert items[0]["value"] == "ok"
    assert items[1]["password"] == "<redacted>"
    assert items[1]["user"] == "alice"


# ---------------------------------------------------------------------------
# redact_value — type dispatch
# ---------------------------------------------------------------------------


def test_redact_value_redacts_secret_str() -> None:
    result = redact_value(SecretStr("top_secret"))
    assert result == "<redacted>"


def test_redact_value_redacts_secret_bytes() -> None:
    result = redact_value(SecretBytes(b"raw_secret_bytes"))
    assert result == "<redacted>"


def test_redact_value_passes_through_plain_int() -> None:
    assert redact_value(42) == 42


def test_redact_value_passes_through_none() -> None:
    assert redact_value(None) is None


# ---------------------------------------------------------------------------
# redact_string — inline pattern redaction
# ---------------------------------------------------------------------------


def test_redact_string_redacts_access_token_equals() -> None:
    result = redact_string("GET /api access_token=abc1234567890")
    assert "abc1234567890" not in result
    assert "access_token=<redacted>" in result


def test_redact_string_redacts_refresh_token_colon() -> None:
    result = redact_string('{"refresh_token": "ref_secret_value"}')
    assert "ref_secret_value" not in result


def test_redact_string_redacts_client_secret_quoted() -> None:
    result = redact_string('client_secret="abc_secret_xyz"')
    assert "abc_secret_xyz" not in result
    assert "client_secret=<redacted>" in result


def test_redact_string_redacts_password_assignment() -> None:
    result = redact_string("password=hunter2_long_enough")
    assert "hunter2_long_enough" not in result


def test_redact_string_leaves_safe_strings_unchanged() -> None:
    safe = "GET /api/health HTTP/1.1"
    assert redact_string(safe) == safe


# ---------------------------------------------------------------------------
# redact_exception — sanitized exception string
# ---------------------------------------------------------------------------


def test_redact_exception_includes_class_name() -> None:
    exc = ValueError("something went wrong")
    result = redact_exception(exc)
    assert "ValueError" in result


def test_redact_exception_does_not_leak_token_substrings() -> None:
    exc = RuntimeError("access_token=supersecrettoken123 was rejected")
    result = redact_exception(exc)
    assert "supersecrettoken123" not in result
    assert "access_token=<redacted>" in result


def test_redact_exception_does_not_include_traceback() -> None:
    try:
        raise ValueError("password=plaintext123")
    except ValueError as exc:
        result = redact_exception(exc)

    assert "Traceback" not in result
    assert "plaintext123" not in result
    assert "ValueError" in result


def test_redact_exception_handles_base_exception() -> None:
    exc = KeyboardInterrupt("password=abc123456")
    result = redact_exception(exc)
    assert "KeyboardInterrupt" in result
    assert "abc123456" not in result


# ---------------------------------------------------------------------------
# redact_log_record — loguru-compatible in-place mutation
# ---------------------------------------------------------------------------


def test_redact_log_record_returns_none() -> None:
    record: dict[str, Any] = {"message": "hello", "extra": {}}
    result = redact_log_record(record)
    assert result is None


def test_redact_log_record_mutates_in_place() -> None:
    record: dict[str, Any] = {"message": "access_token=tok_secret_value123", "extra": {}}
    redact_log_record(record)
    assert "tok_secret_value123" not in record["message"]
    assert "access_token=<redacted>" in record["message"]


def test_redact_log_record_redacts_message() -> None:
    record: dict[str, Any] = {
        "message": "proxy call with password=open_sesame_long",
        "extra": {},
    }
    redact_log_record(record)
    assert "open_sesame_long" not in record["message"]


def test_redact_log_record_redacts_extra_mapping() -> None:
    record: dict[str, Any] = {
        "message": "request executed",
        "extra": {
            "headers": {"authorization": "Bearer tok_secret"},
            "url": "https://example.com",
        },
    }
    redact_log_record(record)
    assert record["extra"]["headers"]["authorization"] == "<redacted>"
    assert record["extra"]["url"] == "https://example.com"


def test_redact_log_record_handles_missing_message() -> None:
    record: dict[str, Any] = {"level": "INFO", "extra": {"cookies": "sid=abc"}}
    redact_log_record(record)
    assert record["extra"]["cookies"] == "<redacted>"


def test_redact_log_record_handles_non_mapping_extra() -> None:
    record: dict[str, Any] = {"message": "hello", "extra": "not_a_dict"}
    # Must not raise; non-mapping extra is left as-is
    redact_log_record(record)
    assert record["extra"] == "not_a_dict"
