"""``sightstalker version`` tests."""

from __future__ import annotations

import json

from typer.testing import CliRunner

import sightstalker
from sightstalker.cli.main import app

runner = CliRunner()


def test_version_human() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert sightstalker.__version__ in result.stdout


def test_version_json() -> None:
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["command"] == "version"
    assert payload["data"]["version"] == sightstalker.__version__
    assert payload["errors"] == []


def test_version_json_stderr_empty() -> None:
    result = runner.invoke(app, ["version", "--json"])
    assert result.stderr == ""
