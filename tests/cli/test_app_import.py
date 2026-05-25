"""Importing the CLI app must be light and must not load browser packages."""

from __future__ import annotations

import subprocess
import sys


def _run_probe(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )


def test_import_cli_main_exposes_app() -> None:
    from sightstalker.cli.main import app

    assert app is not None


def test_import_cli_main_does_not_load_camoufox() -> None:
    # Must be checked in a fresh interpreter: sys.modules is process-global, so
    # other tests importing the adapter would otherwise pollute this assertion.
    probe = (
        "import sys, sightstalker.cli.main;"
        "bad=[m for m in ('camoufox','playwright','sightstalker.engines.camoufox')"
        " if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_cli_does_not_load_web_frameworks() -> None:
    probe = (
        "import sys, sightstalker.cli.main;"
        "bad=[m for m in ('fastapi','uvicorn','loguru','tenacity')"
        " if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stdout + result.stderr


def test_app_has_expected_command_groups() -> None:
    from typer.testing import CliRunner

    from sightstalker.cli.main import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("version", "config", "db", "profile", "session", "run", "diag"):
        assert group in result.stdout
