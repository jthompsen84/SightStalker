"""
sightstalker.cli.config — CLI runtime configuration model and resolution.

Resolves the data directory and database URL from explicit options, then
environment variables, then safe defaults. No persistent config file or
settings store is introduced in CLI-RUNNER-1.

Output safety: the resolved absolute data directory and the raw database URL
are never printed by default. ``config show`` uses the redacted display fields
produced here; the absolute data dir appears only under ``--verbose`` and the
database URL is always passed through ``sanitize_database_url``.
"""

from __future__ import annotations

import os
from pathlib import Path

from sightstalker.models import ToolkitModel

ENV_DATA_DIR = "SIGHTSTALKER_DATA_DIR"
ENV_DATABASE_URL = "SIGHTSTALKER_DATABASE_URL"

DEFAULT_DATA_DIR = "./.sightstalker"
_METADATA_DIR_NAME = "metadata"
_SQLITE_FILE_NAME = "sightstalker.sqlite3"


class CliRuntimeConfig(ToolkitModel):
    """Resolved, immutable CLI runtime configuration.

    ``data_dir`` is an absolute resolved path used internally. ``data_dir_input``
    preserves the original (option/env/default) value for safe display.
    """

    data_dir: Path
    data_dir_input: str | None = None
    database_url: str
    json_output: bool = False
    verbose: bool = False


def _resolve_data_dir(explicit: str | None) -> tuple[Path, str]:
    """Return ``(absolute_resolved_dir, input_value)``."""
    if explicit is not None and explicit.strip() != "":
        raw = explicit
    else:
        env_value = os.environ.get(ENV_DATA_DIR)
        raw = env_value if env_value else DEFAULT_DATA_DIR
    resolved = Path(raw).expanduser().resolve()
    return resolved, raw


def metadata_dir(data_dir: Path) -> Path:
    """Return the metadata subdirectory under ``data_dir``."""
    return data_dir / _METADATA_DIR_NAME


def default_sqlite_path(data_dir: Path) -> Path:
    """Return the default SQLite file path under the metadata directory."""
    return metadata_dir(data_dir) / _SQLITE_FILE_NAME


def _resolve_database_url(explicit: str | None, data_dir: Path) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit
    env_value = os.environ.get(ENV_DATABASE_URL)
    if env_value:
        return env_value
    sqlite_path = default_sqlite_path(data_dir)
    return f"sqlite+aiosqlite:///{sqlite_path}"


def resolve_config(
    *,
    data_dir: str | None,
    database_url: str | None,
    json_output: bool,
    verbose: bool,
) -> CliRuntimeConfig:
    """Resolve all CLI runtime configuration into an immutable model."""
    resolved_dir, input_value = _resolve_data_dir(data_dir)
    resolved_db = _resolve_database_url(database_url, resolved_dir)
    return CliRuntimeConfig(
        data_dir=resolved_dir,
        data_dir_input=input_value,
        database_url=resolved_db,
        json_output=json_output,
        verbose=verbose,
    )


def safe_data_dir_display(config: CliRuntimeConfig) -> str:
    """Return a relative/basename-safe display value for the data dir."""
    raw = config.data_dir_input or DEFAULT_DATA_DIR
    candidate = Path(raw)
    if not candidate.is_absolute():
        return raw
    # Absolute input: avoid leaking the full path; show a basename hint.
    return f".../{config.data_dir.name}"


def safe_path_display(config: CliRuntimeConfig, path: Path) -> str:
    """Display a path relative to the data dir when possible (or its name).

    Under ``--verbose`` the absolute path is returned.
    """
    if config.verbose:
        return str(path)
    try:
        return str(path.resolve().relative_to(config.data_dir))
    except ValueError:
        return path.name


__all__ = [
    "CliRuntimeConfig",
    "DEFAULT_DATA_DIR",
    "ENV_DATABASE_URL",
    "ENV_DATA_DIR",
    "default_sqlite_path",
    "metadata_dir",
    "resolve_config",
    "safe_data_dir_display",
    "safe_path_display",
]
