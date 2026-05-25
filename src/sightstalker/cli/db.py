"""
sightstalker.cli.db — database initialization and migration commands.

``db init`` creates the metadata directory (best-effort ``0o700``), runs the
packaged Alembic migrations to head, and best-effort tightens a SQLite file to
``0o600``. ``db upgrade`` runs migrations to head. Both are idempotent. No raw
SQL or DB-URL credentials are ever printed; migration failures surface as
sanitized persistence errors (exit code 3).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from rich.console import Console

from sightstalker.cli.config import CliRuntimeConfig, metadata_dir, safe_path_display
from sightstalker.cli.errors import CliPersistenceError
from sightstalker.cli.types import CommandOutcome
from sightstalker.persistence import make_alembic_config, sanitize_database_url

_METADATA_DIR_MODE = 0o700
_SQLITE_FILE_MODE = 0o600
_SQLITE_PREFIX = "sqlite+aiosqlite:///"


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except (OSError, NotImplementedError):
        pass


def _sqlite_file_path(database_url: str) -> Path | None:
    """Return the on-disk SQLite path for a file-backed SQLite URL, if any."""
    if not database_url.startswith(_SQLITE_PREFIX):
        return None
    raw = database_url[len(_SQLITE_PREFIX) :]
    if raw in ("", ":memory:"):
        return None
    return Path("/" + raw) if not raw.startswith("/") else Path(raw)


def _run_upgrade(database_url: str) -> None:
    try:
        config = make_alembic_config(database_url)
        command.upgrade(config, "head")
    except Exception as exc:  # noqa: BLE001 - sanitize; never leak URL/SQL
        raise CliPersistenceError(
            f"database migration failed: {type(exc).__name__}"
        ) from None


def init_database(config: CliRuntimeConfig) -> CommandOutcome:
    """Create the metadata directory and migrate to head (idempotent)."""
    meta_dir = metadata_dir(config.data_dir)
    try:
        meta_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CliPersistenceError(
            f"could not create metadata directory: {type(exc).__name__}"
        ) from None
    _chmod_best_effort(meta_dir, _METADATA_DIR_MODE)

    _run_upgrade(config.database_url)

    sqlite_path = _sqlite_file_path(config.database_url)
    if sqlite_path is not None and sqlite_path.exists():
        _chmod_best_effort(sqlite_path, _SQLITE_FILE_MODE)

    safe_url = sanitize_database_url(config.database_url)
    meta_display = safe_path_display(config, meta_dir)
    data = {
        "status": "initialized",
        "database_url": safe_url,
        "metadata_dir": meta_display,
    }

    def human(console: Console) -> None:
        console.print("Database initialized.")
        console.print(f"  metadata dir: {meta_display}")
        console.print(f"  database:     {safe_url}")

    return CommandOutcome(data=data, human=human)


def upgrade_database(config: CliRuntimeConfig) -> CommandOutcome:
    """Run migrations to head (idempotent)."""
    _run_upgrade(config.database_url)
    safe_url = sanitize_database_url(config.database_url)
    data = {"status": "upgraded", "database_url": safe_url}

    def human(console: Console) -> None:
        console.print("Database upgraded to head.")
        console.print(f"  database: {safe_url}")

    return CommandOutcome(data=data, human=human)


__all__ = ["init_database", "upgrade_database"]
