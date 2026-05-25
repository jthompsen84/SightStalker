"""The CLI must expose no web/API/daemon/interaction surface."""

from __future__ import annotations

import sys

from typer.testing import CliRunner

from sightstalker.cli.main import app

runner = CliRunner()

_FORBIDDEN_COMMANDS = [
    "serve",
    "api",
    "web",
    "daemon",
    "schedule",
    "agent",
    "remote",
    "replay-browser",
    "click",
    "type",
    "scrape",
    "login",
    "captcha",
]


def test_forbidden_top_level_commands_absent() -> None:
    help_text = runner.invoke(app, ["--help"]).stdout
    for name in _FORBIDDEN_COMMANDS:
        assert name not in help_text


def test_invoking_forbidden_commands_fails() -> None:
    for name in _FORBIDDEN_COMMANDS:
        result = runner.invoke(app, [name])
        assert result.exit_code != 0, name


def test_no_web_framework_loaded() -> None:
    import importlib

    importlib.import_module("sightstalker.cli.main")
    for forbidden in ("fastapi", "uvicorn", "starlette"):
        assert forbidden not in sys.modules


def test_allowed_command_groups_present() -> None:
    help_text = runner.invoke(app, ["--help"]).stdout
    for group in ("version", "config", "db", "profile", "session", "run", "diag"):
        assert group in help_text
