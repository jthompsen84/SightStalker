"""Diagnostics-local strict redaction tests (spec §15, §428)."""

from __future__ import annotations

from sightstalker.diagnostics.redaction import (
    redact_console_location,
    redact_console_text,
)


def test_redacts_bearer_token() -> None:
    out = redact_console_text("Authorization: Bearer abcdef1234567890")
    assert "abcdef1234567890" not in out
    assert "<redacted>" in out


def test_redacts_jwt_like_token() -> None:
    jwt = "eyJhbGciOi.eyJzdWIiOi.SflKxwRJSMeKKF2QT4"
    out = redact_console_text(f"token is {jwt}")
    assert jwt not in out
    assert "<redacted>" in out


def test_redacts_cookie_header_form() -> None:
    out = redact_console_text("Cookie: session=session-cookie-value; a=b")
    assert "session-cookie-value" not in out


def test_redacts_set_cookie_form() -> None:
    out = redact_console_text("set-cookie: sid=raw-token-123; Path=/")
    assert "raw-token-123" not in out


def test_redacts_key_value_token() -> None:
    out = redact_console_text("access_token=raw-token-123")
    assert "raw-token-123" not in out


def test_plain_text_passes_through() -> None:
    out = redact_console_text("hello world, nothing secret here")
    assert out == "hello world, nothing secret here"


def test_location_none_returns_none() -> None:
    assert redact_console_location(None) is None


def test_location_redacts_sensitive_keys() -> None:
    loc = {"url": "https://x/a", "authorization": "Bearer secret-xyz123456"}
    out = redact_console_location(loc)
    assert out is not None
    assert "secret-xyz123456" not in str(out)


def test_location_redacts_token_in_url_value() -> None:
    loc = {"url": "https://x/cb?access_token=raw-token-123", "lineNumber": 5}
    out = redact_console_location(loc)
    assert out is not None
    assert "raw-token-123" not in str(out)
    assert out["lineNumber"] == 5
