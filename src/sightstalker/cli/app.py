"""
sightstalker.cli.app — Typer command surface.

Defines the local operator CLI: ``version``, ``config show``, ``db init/upgrade``,
``profile create/list/archive``, ``session create/list/archive``, ``run open``,
and ``diag screenshot/trace/console``. Every command resolves runtime config and
runs through the central output wrapper. Global options (``--data-dir``,
``--database-url``, ``--json``, ``--verbose``) are accepted on each command so
they work whether placed before or after the subcommand.

This module imports only lightweight CLI helpers and accepted service facades.
No browser package or adapter is imported here; the engine is resolved lazily
inside ``run``/``diag`` execution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional, cast

import typer
from rich.console import Console

from sightstalker import __version__
from sightstalker.cli import db as db_cmds
from sightstalker.cli import diagnostics as diag_cmds
from sightstalker.cli import profiles as profile_cmds
from sightstalker.cli import runs as run_cmds
from sightstalker.cli import sessions as session_cmds
from sightstalker.cli.config import (
    CliRuntimeConfig,
    resolve_config,
    safe_data_dir_display,
)
from sightstalker.cli.output import run_cli_command
from sightstalker.cli.types import CommandOutcome
from sightstalker.persistence import sanitize_database_url

# Typer's option helpers are intentionally loosely typed; confine the single
# unavoidable "unknown" surface to this wrapper so the rest of the module stays
# strictly typed.
_TYPER_OPTION = cast(
    "Callable[..., Any]",
    typer.Option,  # pyright: ignore[reportUnknownMemberType]
)


def _opt(default: object, *param_decls: str, **kwargs: object) -> Any:
    return _TYPER_OPTION(default, *param_decls, **kwargs)


# Shared global option definitions (reused across commands).
_DATA_DIR = _opt(
    None, "--data-dir", metavar="PATH", help="SightStalker data directory."
)
_DATABASE_URL = _opt(
    None, "--database-url", help="Metadata database URL (credentials redacted)."
)
_JSON = _opt(False, "--json", help="Emit a machine-readable JSON object.")
_VERBOSE = _opt(False, "--verbose", help="Show additional safe detail.")

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="SightStalker local operator CLI (local-only; no network service).",
)
config_app = typer.Typer(no_args_is_help=True, help="Inspect resolved configuration.")
db_app = typer.Typer(no_args_is_help=True, help="Initialize and migrate metadata DB.")
profile_app = typer.Typer(no_args_is_help=True, help="Manage profiles.")
session_app = typer.Typer(no_args_is_help=True, help="Manage sessions.")
run_app = typer.Typer(no_args_is_help=True, help="Run one explicit browser open.")
diag_app = typer.Typer(no_args_is_help=True, help="Capture passive diagnostics.")

app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
app.add_typer(profile_app, name="profile")
app.add_typer(session_app, name="session")
app.add_typer(run_app, name="run")
app.add_typer(diag_app, name="diag")


def _config(
    data_dir: str | None, database_url: str | None, json_output: bool, verbose: bool
) -> CliRuntimeConfig:
    return resolve_config(
        data_dir=data_dir,
        database_url=database_url,
        json_output=json_output,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command("version")
def version(
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Print the SightStalker version."""
    cfg = _config(data_dir, database_url, json_output, verbose)

    def handler() -> CommandOutcome:
        data = {"version": __version__}

        def human(console: Console) -> None:
            console.print(__version__)

        return CommandOutcome(data=data, human=human)

    run_cli_command(
        "version", json_output=cfg.json_output, verbose=cfg.verbose, handler=handler
    )


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------


@config_app.command("show")
def config_show(
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Show resolved configuration with redacted paths and DB URL."""
    cfg = _config(data_dir, database_url, json_output, verbose)

    def handler() -> CommandOutcome:
        display = safe_data_dir_display(cfg)
        resolved = str(cfg.data_dir) if cfg.verbose else "<redacted>"
        data = {
            "version": __version__,
            "data_dir_input": cfg.data_dir_input,
            "data_dir_display": display,
            "data_dir_resolved": resolved,
            "database_url": sanitize_database_url(cfg.database_url),
            "json_output": cfg.json_output,
            "verbose": cfg.verbose,
        }

        def human(console: Console) -> None:
            console.print(f"version:       {__version__}")
            console.print(f"data dir:      {display}")
            if cfg.verbose:
                console.print(f"data dir path: {resolved}")
            console.print(f"database:      {data['database_url']}")

        return CommandOutcome(data=data, human=human)

    run_cli_command(
        "config.show", json_output=cfg.json_output, verbose=cfg.verbose, handler=handler
    )


# ---------------------------------------------------------------------------
# db
# ---------------------------------------------------------------------------


@db_app.command("init")
def db_init(
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Create the metadata directory and migrate to head (idempotent)."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "db.init",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: db_cmds.init_database(cfg),
    )


@db_app.command("upgrade")
def db_upgrade(
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Run migrations to head (idempotent)."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "db.upgrade",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: db_cmds.upgrade_database(cfg),
    )


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------


@profile_app.command("create")
def profile_create(
    name: str = _opt(..., "--name", help="Human-readable profile name."),
    profile_id: Optional[str] = _opt(None, "--profile-id"),
    profile_dir: Optional[str] = _opt(None, "--profile-dir"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Create a profile (defaults its directory to the SessionPaths authority)."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "profile.create",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: profile_cmds.create_profile(
            cfg, name=name, profile_id=profile_id, profile_dir=profile_dir
        ),
    )


@profile_app.command("list")
def profile_list(
    include_archived: bool = _opt(False, "--include-archived"),
    limit: Optional[int] = _opt(None, "--limit"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """List profiles."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "profile.list",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: profile_cmds.list_profiles(
            cfg, include_archived=include_archived, limit=limit
        ),
    )


@profile_app.command("archive")
def profile_archive(
    profile_id: str = _opt(..., "--profile-id"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Archive a profile (no deletion, no cascade)."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "profile.archive",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: profile_cmds.archive_profile(cfg, profile_id=profile_id),
    )


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------


@session_app.command("create")
def session_create(
    name: str = _opt(..., "--name"),
    profile_id: str = _opt(..., "--profile-id"),
    session_id: Optional[str] = _opt(None, "--session-id"),
    engine: str = _opt("camoufox", "--engine"),
    headed: bool = _opt(False, "--headed/--headless"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Create a session bound to an existing profile."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "session.create",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: session_cmds.create_session(
            cfg,
            name=name,
            profile_id=profile_id,
            session_id=session_id,
            engine=engine,
            headed=headed,
        ),
    )


@session_app.command("list")
def session_list(
    profile_id: str = _opt(..., "--profile-id"),
    include_archived: bool = _opt(False, "--include-archived"),
    limit: Optional[int] = _opt(None, "--limit"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """List sessions for a profile (profile id required)."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "session.list",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: session_cmds.list_sessions(
            cfg,
            profile_id=profile_id,
            include_archived=include_archived,
            limit=limit,
        ),
    )


@session_app.command("archive")
def session_archive(
    session_id: str = _opt(..., "--session-id"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Archive a session (no deletion, no cascade)."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "session.archive",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: session_cmds.archive_session(cfg, session_id=session_id),
    )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@run_app.command("open")
def run_open_cmd(
    session_id: str = _opt(..., "--session-id"),
    url: str = _opt(..., "--url"),
    headed: Optional[bool] = _opt(None, "--headed/--headless"),
    timeout_ms: Optional[int] = _opt(None, "--timeout-ms"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Open a session and navigate exactly once to a URL."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "run.open",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: run_cmds.run_open(
            cfg,
            session_id=session_id,
            url=url,
            headed_override=headed,
            timeout_ms=timeout_ms,
        ),
    )


# ---------------------------------------------------------------------------
# diag
# ---------------------------------------------------------------------------


@diag_app.command("screenshot")
def diag_screenshot_cmd(
    session_id: str = _opt(..., "--session-id"),
    url: str = _opt(..., "--url"),
    headed: Optional[bool] = _opt(None, "--headed/--headless"),
    timeout_ms: Optional[int] = _opt(None, "--timeout-ms"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Capture a screenshot for an explicitly supplied URL."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "diag.screenshot",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: diag_cmds.diag_screenshot(
            cfg,
            session_id=session_id,
            url=url,
            headed_override=headed,
            timeout_ms=timeout_ms,
        ),
    )


@diag_app.command("trace")
def diag_trace_cmd(
    session_id: str = _opt(..., "--session-id"),
    url: str = _opt(..., "--url"),
    headed: Optional[bool] = _opt(None, "--headed/--headless"),
    timeout_ms: Optional[int] = _opt(None, "--timeout-ms"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Capture a trace for an explicitly supplied URL."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "diag.trace",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: diag_cmds.diag_trace(
            cfg,
            session_id=session_id,
            url=url,
            headed_override=headed,
            timeout_ms=timeout_ms,
        ),
    )


@diag_app.command("console")
def diag_console_cmd(
    session_id: str = _opt(..., "--session-id"),
    url: str = _opt(..., "--url"),
    headed: Optional[bool] = _opt(None, "--headed/--headless"),
    timeout_ms: Optional[int] = _opt(None, "--timeout-ms"),
    data_dir: Optional[str] = _DATA_DIR,
    database_url: Optional[str] = _DATABASE_URL,
    json_output: bool = _JSON,
    verbose: bool = _VERBOSE,
) -> None:
    """Capture console output for an explicitly supplied URL."""
    cfg = _config(data_dir, database_url, json_output, verbose)
    run_cli_command(
        "diag.console",
        json_output=cfg.json_output,
        verbose=cfg.verbose,
        handler=lambda: diag_cmds.diag_console(
            cfg,
            session_id=session_id,
            url=url,
            headed_override=headed,
            timeout_ms=timeout_ms,
        ),
    )


__all__ = ["app"]
