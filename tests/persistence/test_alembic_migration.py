"""Alembic migration tests (spec 19.4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command

from sightstalker.persistence import make_alembic_config

_REQUIRED_TABLES = {
    "profiles",
    "sessions",
    "runs",
    "browser_contexts",
    "artifacts",
    "health_records",
}


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows}


def test_make_alembic_config_resolves_packaged_migrations() -> None:
    cfg = make_alembic_config("sqlite+aiosqlite:///:memory:")
    location = cfg.get_main_option("script_location")
    assert location is not None
    assert "persistence" in location
    assert (Path(location) / "env.py").exists()


def test_upgrade_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "u.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    assert _REQUIRED_TABLES <= _tables(db)


def test_downgrade_removes_tables(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    remaining = _tables(db)
    assert _REQUIRED_TABLES.isdisjoint(remaining)


def test_migration_files_packaged() -> None:
    cfg = make_alembic_config("sqlite+aiosqlite:///:memory:")
    location = Path(cfg.get_main_option("script_location") or "")
    assert (location / "versions" / "0001_persistence_1_initial.py").exists()


def test_migration_against_temp_sqlite_file(tmp_path: Path) -> None:
    db = tmp_path / "temp.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    assert db.exists()
    assert "alembic_version" in _tables(db)


def test_async_url_supported(tmp_path: Path) -> None:
    # The env uses async_engine_from_config; an aiosqlite URL must work.
    db = tmp_path / "async.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    assert _REQUIRED_TABLES <= _tables(db)


def test_migration_does_not_require_camoufox(tmp_path: Path) -> None:
    import sys

    db = tmp_path / "nocam.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    assert "camoufox" not in sys.modules


def test_migration_does_not_require_web_cli(tmp_path: Path) -> None:
    import sys

    db = tmp_path / "noweb.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    for mod in ("typer", "fastapi", "uvicorn", "rich", "loguru"):
        assert mod not in sys.modules


def test_restrictive_fk_after_migration(tmp_path: Path) -> None:
    db = tmp_path / "fk.db"
    cfg = make_alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    try:
        # SQLite reports ON DELETE action in foreign_key_list pragma.
        fks = con.execute("PRAGMA foreign_key_list(sessions)").fetchall()
    finally:
        con.close()
    # Column index 6 is the on_delete action.
    actions = {row[6] for row in fks}
    assert actions == {"RESTRICT"} or "RESTRICT" in actions
