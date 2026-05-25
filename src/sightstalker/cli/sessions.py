"""
sightstalker.cli.sessions — session create/list/archive commands.

``session create`` builds a deliberately minimal, secret-free ``SessionConfig``
(engine name + headed/headless mode only — no proxy password, env, headers, or
path-bearing fields), verifies the profile exists, and persists a
``SessionRecord`` in one transaction.

``session list`` requires ``--profile-id`` because the accepted repository
exposes ``list_for_profile`` and not a list-all API (deferred). ``archive``
only flips the archived flag — no deletion, no cascade.
"""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.table import Table

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.context import cli_persistence
from sightstalker.cli.errors import CliUsageError
from sightstalker.cli.types import (
    CommandOutcome,
    require_profile_id,
    require_session_id,
    validate_engine_name,
    validate_limit,
)
from sightstalker.ids import new_session_id
from sightstalker.models import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserMode,
    SessionConfig,
    SessionId,
    SessionRecord,
)
from sightstalker.persistence import (
    ProfileRepository,
    SessionRepository,
    database_session,
)


def _session_summary(session: SessionRecord) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "name": session.name,
        "profile_id": session.profile_id,
        "engine_name": session.config.launch.engine_name,
        "mode": session.config.launch.mode,
        "health_status": session.health_status,
        "archived": session.archived,
    }


def _build_safe_config(*, engine: str, headed: bool) -> SessionConfig:
    mode: BrowserMode = "headed" if headed else "headless"
    launch = BrowserLaunchConfig(
        engine_name=validate_engine_name(engine),
        mode=mode,
    )
    return SessionConfig(launch=launch, context=BrowserContextConfig())


def create_session(
    config: CliRuntimeConfig,
    *,
    name: str,
    profile_id: str,
    session_id: str | None,
    engine: str,
    headed: bool,
) -> CommandOutcome:
    """Create and persist a session bound to an existing profile."""
    if name.strip() == "":
        raise CliUsageError("--name must not be empty")

    pid = require_profile_id(profile_id)
    sid: SessionId = (
        require_session_id(session_id)
        if session_id is not None and session_id != ""
        else new_session_id()
    )
    session_config = _build_safe_config(engine=engine, headed=headed)
    record = SessionRecord(
        session_id=sid, name=name, profile_id=pid, config=session_config
    )

    async def _impl() -> SessionRecord:
        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                async with session.begin():
                    # Confirm the profile exists before creating the session.
                    profiles = ProfileRepository(session, data_dir=config.data_dir)
                    await profiles.require(pid)
                    sessions = SessionRepository(session)
                    return await sessions.create(record)

    created = asyncio.run(_impl())
    summary = _session_summary(created)

    def human(console: Console) -> None:
        console.print(f"Created session [bold]{created.session_id}[/bold]")
        console.print(f"  name:    {created.name}")
        console.print(f"  profile: {created.profile_id}")
        console.print(f"  engine:  {summary['engine_name']} ({summary['mode']})")

    return CommandOutcome(data=summary, human=human)


def list_sessions(
    config: CliRuntimeConfig,
    *,
    profile_id: str,
    include_archived: bool,
    limit: int | None,
) -> CommandOutcome:
    """List sessions for a profile in deterministic repository order."""
    pid = require_profile_id(profile_id)
    checked_limit = validate_limit(limit)

    async def _impl() -> list[SessionRecord]:
        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                repo = SessionRepository(session)
                return await repo.list_for_profile(
                    pid, include_archived=include_archived, limit=checked_limit
                )

    sessions = asyncio.run(_impl())
    rows = [_session_summary(s) for s in sessions]

    def human(console: Console) -> None:
        if not rows:
            console.print("No sessions found.")
            return
        table = Table(title=f"Sessions for {pid}")
        table.add_column("session_id")
        table.add_column("name")
        table.add_column("engine")
        table.add_column("mode")
        table.add_column("archived")
        for row in rows:
            table.add_row(
                str(row["session_id"]),
                str(row["name"]),
                str(row["engine_name"]),
                str(row["mode"]),
                str(row["archived"]),
            )
        console.print(table)

    return CommandOutcome(data=rows, human=human)


def archive_session(config: CliRuntimeConfig, *, session_id: str) -> CommandOutcome:
    """Archive a session (no deletion, no cascade)."""
    sid = require_session_id(session_id)

    async def _impl() -> SessionRecord:
        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                async with session.begin():
                    repo = SessionRepository(session)
                    return await repo.archive(sid)

    archived = asyncio.run(_impl())
    summary = _session_summary(archived)

    def human(console: Console) -> None:
        console.print(f"Archived session [bold]{archived.session_id}[/bold]")

    return CommandOutcome(data=summary, human=human)


__all__ = ["archive_session", "create_session", "list_sessions"]
