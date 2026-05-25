"""``sightstalker config show`` tests: redaction of paths and DB URL."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from sightstalker.cli.main import app

runner = CliRunner()


def test_config_show_json_redacts_resolved_path() -> None:
    result = runner.invoke(app, ["config", "show", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["data_dir_resolved"] == "<redacted>"
    # Default human/JSON output must not contain an absolute path.
    assert not str(data["data_dir_display"]).startswith("/")


def test_config_show_verbose_reveals_resolved_path() -> None:
    result = runner.invoke(app, ["config", "show", "--json", "--verbose"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["data_dir_resolved"] != "<redacted>"
    assert data["verbose"] is True


def test_config_show_sanitizes_database_url() -> None:
    secret_url = "postgresql+asyncpg://user:db-password-xyz@host:5432/db"
    result = runner.invoke(
        app, ["config", "show", "--json", "--database-url", secret_url]
    )
    assert result.exit_code == 0
    blob = result.stdout
    assert "db-password-xyz" not in blob
    data = json.loads(blob)["data"]
    assert "db-password-xyz" not in data["database_url"]
    assert "host:5432" in data["database_url"]


def test_config_show_default_db_url_has_no_credentials() -> None:
    result = runner.invoke(app, ["config", "show", "--json"])
    data = json.loads(result.stdout)["data"]
    assert "@" not in data["database_url"]
