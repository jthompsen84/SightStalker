"""Session command tests: create/list/archive, required profile id, limits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from sightstalker.cli.main import app


def _base(data_dir: Path) -> list[str]:
    return ["--data-dir", str(data_dir), "--json"]


def _make_profile(runner: CliRunner, data_dir: Path) -> str:
    res = runner.invoke(app, ["profile", "create", "--name", "p", *_base(data_dir)])
    assert res.exit_code == 0, res.stdout
    return cast(str, json.loads(res.stdout)["data"]["profile_id"])


def test_session_create_and_list(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    pid = _make_profile(runner, initialized_db_dir)
    created = runner.invoke(
        app,
        ["session", "create", "--name", "s1", "--profile-id", pid,
         *_base(initialized_db_dir)],
    )
    assert created.exit_code == 0, created.stdout
    data = json.loads(created.stdout)["data"]
    assert data["session_id"].startswith("sess_")
    assert data["engine_name"] == "camoufox"
    assert data["mode"] == "headless"

    listed = runner.invoke(
        app, ["session", "list", "--profile-id", pid, *_base(initialized_db_dir)]
    )
    assert listed.exit_code == 0
    rows = json.loads(listed.stdout)["data"]
    assert any(r["session_id"] == data["session_id"] for r in rows)


def test_session_create_headed_flag(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    pid = _make_profile(runner, initialized_db_dir)
    created = runner.invoke(
        app,
        ["session", "create", "--name", "s", "--profile-id", pid, "--headed",
         *_base(initialized_db_dir)],
    )
    assert created.exit_code == 0
    assert json.loads(created.stdout)["data"]["mode"] == "headed"


def test_session_list_requires_profile_id(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    # Missing required --profile-id is a Click usage error (exit code 2).
    result = runner.invoke(app, ["session", "list", *_base(initialized_db_dir)])
    assert result.exit_code == 2


def test_session_list_rejects_non_positive_limit(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    pid = _make_profile(runner, initialized_db_dir)
    result = runner.invoke(
        app,
        ["session", "list", "--profile-id", pid, "--limit", "-1",
         *_base(initialized_db_dir)],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["errors"][0]["type"] == "UsageError"


def test_session_archive(runner: CliRunner, initialized_db_dir: Path) -> None:
    pid = _make_profile(runner, initialized_db_dir)
    sid = cast(
        str,
        json.loads(
            runner.invoke(
                app,
                ["session", "create", "--name", "s", "--profile-id", pid,
                 *_base(initialized_db_dir)],
            ).stdout
        )["data"]["session_id"],
    )
    archived = runner.invoke(
        app, ["session", "archive", "--session-id", sid, *_base(initialized_db_dir)]
    )
    assert archived.exit_code == 0
    assert json.loads(archived.stdout)["data"]["archived"] is True


def test_session_create_invalid_engine_rejected(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    pid = _make_profile(runner, initialized_db_dir)
    result = runner.invoke(
        app,
        ["session", "create", "--name", "s", "--profile-id", pid,
         "--engine", "chromium", *_base(initialized_db_dir)],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["ok"] is False
