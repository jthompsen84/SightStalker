"""Error mapping and exit-code tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sightstalker.cli import runtime as cli_runtime
from sightstalker.cli.errors import (
    CliBrowserError,
    CliPersistenceError,
    CliSecurityError,
    map_exception,
)
from sightstalker.cli.exit_codes import (
    EXIT_BROWSER,
    EXIT_PERSISTENCE,
    EXIT_SECURITY,
    EXIT_USAGE,
)
from sightstalker.cli.main import app


def test_unsupported_engine_is_browser_error() -> None:
    with pytest.raises(CliBrowserError):
        cli_runtime.create_engine_for_name("playwright_chromium")


def test_missing_schema_maps_to_persistence_with_guidance(
    runner: CliRunner, data_dir: Path
) -> None:
    # Fresh data dir, DB never initialized: a DB-backed command fails clean.
    result = runner.invoke(
        app, ["profile", "list", "--data-dir", str(data_dir), "--json"]
    )
    assert result.exit_code == EXIT_PERSISTENCE
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "db init" in payload["errors"][0]["message"]


def test_missing_session_maps_to_persistence(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", "sess_absent_00000000",
         "--url", "about:blank", "--data-dir", str(initialized_db_dir), "--json"],
    )
    assert result.exit_code == EXIT_PERSISTENCE
    assert json.loads(result.stdout)["ok"] is False


def test_unsafe_url_maps_to_security_exit_code(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", "sess_absent_00000000",
         "--url", "file:///etc/passwd", "--data-dir", str(initialized_db_dir),
         "--json"],
    )
    assert result.exit_code == EXIT_SECURITY
    assert json.loads(result.stdout)["errors"][0]["type"] == "SecurityError"


def test_map_exception_for_cli_errors() -> None:
    code, entry, _w = map_exception(CliSecurityError("nope"))
    assert code == EXIT_SECURITY
    assert entry["type"] == "SecurityError"

    code, entry, _w = map_exception(CliPersistenceError("db down"))
    assert code == EXIT_PERSISTENCE

    code, _entry, _w = map_exception(CliBrowserError("no browser"))
    assert code == EXIT_BROWSER


def test_map_exception_unknown_is_general() -> None:
    code, entry, _w = map_exception(RuntimeError("boom token=raw-token-123"))
    assert code == 1
    assert "raw-token-123" not in entry["message"]


def test_usage_error_exit_code_constant() -> None:
    assert EXIT_USAGE == 2
