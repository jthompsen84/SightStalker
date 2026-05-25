"""JSON envelope contract tests across success and failure."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from sightstalker.cli.main import app

runner = CliRunner()

_ENVELOPE_KEYS = {"ok", "command", "data", "warnings", "errors"}


def test_json_success_envelope_shape() -> None:
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == _ENVELOPE_KEYS
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_json_failure_envelope_shape_invalid_url(
    runner: CliRunner, initialized_db_dir: object
) -> None:
    # Empty/scheme-less URL is a usage failure (exit 2) in JSON shape.
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", "sess_x_00000000", "--url", "not-a-url",
         "--data-dir", str(initialized_db_dir), "--json"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == _ENVELOPE_KEYS
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["errors"][0]["type"] == "UsageError"


def test_json_failure_invalid_id() -> None:
    result = runner.invoke(
        app, ["profile", "archive", "--profile-id", "bad-id", "--json"]
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_json_failure_invalid_limit(
    runner: CliRunner, initialized_db_dir: object
) -> None:
    result = runner.invoke(
        app, ["profile", "list", "--limit", "0", "--data-dir",
              str(initialized_db_dir), "--json"]
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["ok"] is False


def test_json_success_stdout_is_single_object() -> None:
    result = runner.invoke(app, ["version", "--json"])
    # Exactly one JSON object, one trailing newline, nothing else.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    json.loads(lines[0])


def test_json_success_stderr_empty_without_verbose() -> None:
    result = runner.invoke(app, ["version", "--json"])
    assert result.stderr == ""
