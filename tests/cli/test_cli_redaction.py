"""CLI redaction tests: URL/title/message sanitizers and refusals."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from sightstalker.cli import runs as run_cmds
from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.errors import CliSecurityError, CliUsageError
from sightstalker.cli.redaction import (
    prepare_navigation_url,
    sanitize_cli_message,
    sanitize_title_for_output,
    sanitize_url_for_metadata,
)

from tests.cli.conftest import FakeEngine


def test_url_query_secret_redacted() -> None:
    out = sanitize_url_for_metadata("https://h/p?api_key=raw-token-123&q=ok")
    assert "raw-token-123" not in out
    assert "q=ok" in out


def test_url_fragment_secret_redacted() -> None:
    out = sanitize_url_for_metadata("https://h/p#access_token=Bearer-raw-secret")
    assert "raw-secret" not in out


def test_data_url_body_redacted() -> None:
    raw, meta = prepare_navigation_url("data:text/html,<h1>session-cookie-value</h1>")
    assert meta == "data:text/html,<redacted>"
    assert "session-cookie-value" not in meta
    # raw retains the body for the single in-memory goto, but meta does not.
    assert "session-cookie-value" in raw


def test_data_url_base64_refused() -> None:
    with pytest.raises(CliSecurityError):
        prepare_navigation_url("data:text/html;base64,SGVsbG8=")


def test_data_url_oversize_refused() -> None:
    big = "data:text/html," + ("a" * 5000)
    with pytest.raises(CliSecurityError):
        prepare_navigation_url(big)


def test_embedded_credentials_refused() -> None:
    with pytest.raises(CliSecurityError):
        prepare_navigation_url("https://user:proxy-password-123@host/")


def test_file_scheme_refused() -> None:
    with pytest.raises(CliSecurityError):
        prepare_navigation_url("file:///etc/passwd")


def test_control_characters_refused() -> None:
    with pytest.raises(CliSecurityError):
        prepare_navigation_url("https://host/\npath")


def test_empty_url_is_usage_error() -> None:
    with pytest.raises(CliUsageError):
        prepare_navigation_url("   ")


def test_missing_scheme_is_usage_error() -> None:
    with pytest.raises(CliUsageError):
        prepare_navigation_url("example.com/path")


def test_title_redacted_and_capped() -> None:
    raw = "x\x07y refresh-token-abc token=raw-token-123 " + ("z" * 1000)
    out = sanitize_title_for_output(raw)
    assert out is not None
    assert "\x07" not in out
    assert len(out) <= 512
    assert "raw-token-123" not in out


def test_message_sanitizer_strips_and_redacts() -> None:
    out = sanitize_cli_message("oops password=db-password-xyz\x00")
    assert "\x00" not in out
    assert "db-password-xyz" not in out


def test_run_open_output_has_no_raw_secrets(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    def factory(engine_name: str) -> FakeEngine:
        return fake_engine

    outcome = run_cmds.run_open(
        config,
        session_id=sid,
        url="https://example.com/?token=raw-token-123",
        headed_override=None,
        timeout_ms=None,
        engine_factory=factory,
    )
    blob = json.dumps(cast(dict[str, Any], outcome.data))
    for forbidden in (
        "raw-token-123",
        "session-cookie-value",
        "proxy-password-123",
        "refresh-token-abc",
        "db-password-xyz",
    ):
        assert forbidden not in blob
