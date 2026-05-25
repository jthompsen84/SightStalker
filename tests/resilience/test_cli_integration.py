"""CLI integration tests for the resilience taxonomy.

These verify that the v0.4.0 JSON envelope and public ``type`` labels are
preserved while the new taxonomy fields are added, that exit codes are stable,
that no automatic retry was introduced (operations attempted exactly once), and
that no raw secrets leak.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.main import app
from tests.cli.conftest import FakeEngine


def _args(config: CliRuntimeConfig) -> list[str]:
    return ["--data-dir", str(config.data_dir), "--database-url", config.database_url]


def _failure(result: Any) -> dict[str, Any]:
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    return cast(dict[str, Any], payload["errors"][0])


def test_usage_failure_preserves_label_and_adds_kind(
    runner: CliRunner, initialized_config: CliRuntimeConfig
) -> None:
    # Invalid profile id → usage error.
    result = runner.invoke(
        app,
        ["profile", "create", "--name", "x", "--profile-id", "bad id!", "--json",
         *_args(initialized_config)],
    )
    assert result.exit_code == 2
    entry = _failure(result)
    assert entry["type"] == "UsageError"
    assert entry["kind"] == "usage"
    assert entry["exit_code"] == 2


def test_persistence_failure_label_and_guidance(
    runner: CliRunner, cli_config: CliRuntimeConfig
) -> None:
    # DB never initialized → persistence error with db init guidance.
    result = runner.invoke(app, ["profile", "list", "--json", *_args(cli_config)])
    assert result.exit_code == 3
    entry = _failure(result)
    assert entry["type"] == "PersistenceError"
    assert entry["kind"] == "persistence"
    assert "db init" in entry["message"]


def test_security_failure_label(
    runner: CliRunner, initialized_config: CliRuntimeConfig,
    patch_engine: FakeEngine,
) -> None:
    # file:// scheme is a security refusal (exit 6).
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid, "--url", "file:///etc/passwd",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code == 6
    entry = _failure(result)
    assert entry["type"] == "SecurityError"
    assert entry["kind"] == "security_refusal"


def test_json_envelope_shape_preserved(
    runner: CliRunner, cli_config: CliRuntimeConfig
) -> None:
    result = runner.invoke(app, ["profile", "list", "--json", *_args(cli_config)])
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"ok", "command", "data", "warnings", "errors"}
    assert payload["data"] is None
    entry = payload["errors"][0]
    # New taxonomy fields present alongside the stable type/message.
    for field in (
        "type", "message", "kind", "severity", "recoverability", "exit_code",
        "code", "details",
    ):
        assert field in entry


def test_successful_command_unchanged_except_version(
    runner: CliRunner, initialized_config: CliRuntimeConfig
) -> None:
    result = runner.invoke(
        app, ["profile", "create", "--name", "ok", "--json", *_args(initialized_config)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_json_success_stderr_empty(
    runner: CliRunner, initialized_config: CliRuntimeConfig
) -> None:
    result = runner.invoke(
        app, ["profile", "create", "--name", "ok2", "--json", *_args(initialized_config)]
    )
    assert result.exit_code == 0
    assert result.stderr == ""


def test_no_raw_secrets_in_failure_output(
    runner: CliRunner, initialized_config: CliRuntimeConfig,
    patch_engine: FakeEngine,
) -> None:
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid,
         "--url", "https://example.com/?api_key=raw-token-123",
         "--json", *_args(initialized_config)],
    )
    combined = result.stdout + (result.stderr or "")
    assert "raw-token-123" not in combined


def test_run_open_navigates_exactly_once(
    runner: CliRunner, initialized_config: CliRuntimeConfig,
    patch_engine: FakeEngine,
) -> None:
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid, "--url", "https://example.com/",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code == 0
    total_gotos = sum(
        page.goto_calls
        for ctx in patch_engine.runtime.contexts
        for page in ctx.pages
    )
    assert total_gotos == 1


def test_goto_failure_attempted_exactly_once(
    runner: CliRunner, initialized_config: CliRuntimeConfig,
    monkeypatch: pytest.MonkeyPatch,
    fake_engine: FakeEngine,
) -> None:
    # Make navigation fail and assert it is attempted exactly once (no retry).
    attempts = {"n": 0}

    async def failing_goto(
        self: Any, url: str, *, wait_until: str = "load",
        timeout_ms: int | None = None,
    ) -> None:
        attempts["n"] += 1
        raise RuntimeError("navigation boom")

    from tests.cli.conftest import FakePage

    def _engine_factory(name: str) -> FakeEngine:
        return fake_engine

    monkeypatch.setattr(FakePage, "goto", failing_goto)
    monkeypatch.setattr(
        "sightstalker.cli.runtime.create_engine_for_name",
        _engine_factory,
    )
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid, "--url", "https://example.com/",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code != 0
    assert attempts["n"] == 1


def _make_session(
    runner: CliRunner, config: CliRuntimeConfig
) -> str:
    args = _args(config)
    prof = runner.invoke(
        app, ["profile", "create", "--name", "p", "--json", *args]
    )
    pid = json.loads(prof.stdout)["data"]["profile_id"]
    sess = runner.invoke(
        app,
        ["session", "create", "--name", "s", "--profile-id", pid, "--json",
         *args],
    )
    return cast(str, json.loads(sess.stdout)["data"]["session_id"])
