"""Profile command tests: create/list/archive, profile-dir and limit policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from typer.testing import CliRunner

from sightstalker.cli.main import app
from sightstalker.sessions.paths import SessionPaths


def _base(data_dir: Path) -> list[str]:
    return ["--data-dir", str(data_dir), "--json"]


def test_profile_create_generates_valid_id(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    result = runner.invoke(
        app, ["profile", "create", "--name", "p1", *_base(initialized_db_dir)]
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)["data"]
    assert data["profile_id"].startswith("prof_")
    # Output path is relative/redacted, not absolute.
    assert not str(data["profile_dir"]).startswith("/")


def test_profile_create_custom_dir_must_match_authority(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    pid = "prof_custom_00000001"
    authority = SessionPaths(initialized_db_dir.resolve()).profile_dir(
        cast(Any, pid)
    )
    ok = runner.invoke(
        app,
        [
            "profile", "create", "--name", "p", "--profile-id", pid,
            "--profile-dir", str(authority), *_base(initialized_db_dir),
        ],
    )
    assert ok.exit_code == 0, ok.stdout

    bad = runner.invoke(
        app,
        [
            "profile", "create", "--name", "p2", "--profile-id",
            "prof_custom_00000002", "--profile-dir", "/tmp/somewhere-else",
            *_base(initialized_db_dir),
        ],
    )
    assert bad.exit_code == 2
    assert json.loads(bad.stdout)["ok"] is False


def test_profile_list_and_archive(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    created = json.loads(
        runner.invoke(
            app, ["profile", "create", "--name", "p1", *_base(initialized_db_dir)]
        ).stdout
    )["data"]
    pid = created["profile_id"]

    listed = runner.invoke(app, ["profile", "list", *_base(initialized_db_dir)])
    assert listed.exit_code == 0
    rows = json.loads(listed.stdout)["data"]
    assert any(r["profile_id"] == pid for r in rows)

    archived = runner.invoke(
        app, ["profile", "archive", "--profile-id", pid, *_base(initialized_db_dir)]
    )
    assert archived.exit_code == 0
    assert json.loads(archived.stdout)["data"]["archived"] is True

    # Archived profile hidden by default, visible with --include-archived.
    default_rows = json.loads(
        runner.invoke(app, ["profile", "list", *_base(initialized_db_dir)]).stdout
    )["data"]
    assert all(r["profile_id"] != pid for r in default_rows)
    all_rows = json.loads(
        runner.invoke(
            app,
            ["profile", "list", "--include-archived", *_base(initialized_db_dir)],
        ).stdout
    )["data"]
    assert any(r["profile_id"] == pid for r in all_rows)


def test_profile_list_rejects_non_positive_limit(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    result = runner.invoke(
        app, ["profile", "list", "--limit", "0", *_base(initialized_db_dir)]
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["type"] == "UsageError"


def test_profile_create_invalid_id_returns_json_failure(
    runner: CliRunner, initialized_db_dir: Path
) -> None:
    result = runner.invoke(
        app,
        ["profile", "create", "--name", "p", "--profile-id", "not-valid",
         *_base(initialized_db_dir)],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["ok"] is False
