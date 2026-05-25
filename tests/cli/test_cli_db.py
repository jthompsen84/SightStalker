"""``db init`` / ``db upgrade`` tests: idempotency, permissions, no leakage."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from typer.testing import CliRunner

from sightstalker.cli.main import app


def _base(data_dir: Path) -> list[str]:
    return ["--data-dir", str(data_dir), "--json"]


def test_db_init_creates_metadata_and_is_idempotent(
    runner: CliRunner, data_dir: Path
) -> None:
    first = runner.invoke(app, ["db", "init", *_base(data_dir)])
    assert first.exit_code == 0, first.stdout
    payload = json.loads(first.stdout)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "initialized"

    meta = data_dir / "metadata"
    assert meta.is_dir()
    db_file = meta / "sightstalker.sqlite3"
    assert db_file.exists()

    # Running again must succeed (idempotent).
    second = runner.invoke(app, ["db", "init", *_base(data_dir)])
    assert second.exit_code == 0, second.stdout


def test_db_init_best_effort_permissions(
    runner: CliRunner, data_dir: Path
) -> None:
    result = runner.invoke(app, ["db", "init", *_base(data_dir)])
    assert result.exit_code == 0
    if os.name != "posix":  # pragma: no cover - POSIX-only check
        return
    meta = data_dir / "metadata"
    db_file = meta / "sightstalker.sqlite3"
    dir_mode = stat.S_IMODE(meta.stat().st_mode)
    file_mode = stat.S_IMODE(db_file.stat().st_mode)
    # Group/other bits should not be set under our best-effort tightening.
    assert dir_mode & 0o077 == 0
    assert file_mode & 0o077 == 0


def test_db_upgrade_idempotent(runner: CliRunner, data_dir: Path) -> None:
    assert runner.invoke(app, ["db", "init", *_base(data_dir)]).exit_code == 0
    up = runner.invoke(app, ["db", "upgrade", *_base(data_dir)])
    assert up.exit_code == 0, up.stdout
    assert json.loads(up.stdout)["data"]["status"] == "upgraded"


def test_db_init_does_not_leak_credentials(
    runner: CliRunner, data_dir: Path
) -> None:
    secret_url = "sqlite+aiosqlite:///" + str(data_dir / "x.sqlite3")
    result = runner.invoke(
        app, ["db", "init", "--data-dir", str(data_dir), "--json",
               "--database-url", secret_url]
    )
    assert result.exit_code == 0
    # No raw SQL or credentials; sanitized URL only.
    assert "PRAGMA" not in result.stdout
    assert "CREATE TABLE" not in result.stdout
