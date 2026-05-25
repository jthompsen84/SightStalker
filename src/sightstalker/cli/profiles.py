"""
sightstalker.cli.profiles — profile create/list/archive commands.

Profiles are SightStalker-owned state containers. ``profile create`` mints (or
accepts) a profile id, defaults the profile directory to the ``SessionPaths``
authority, and persists a ``ProfileRecord`` in one transaction. A custom
``--profile-dir`` is accepted only if it resolves to exactly that authority
path; arbitrary directories are deferred to a future profile-registry PR.

No files or rows are deleted: ``archive`` only flips the archived flag.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.table import Table

from sightstalker.cli.config import CliRuntimeConfig, safe_path_display
from sightstalker.cli.context import cli_persistence
from sightstalker.cli.errors import CliUsageError
from sightstalker.cli.types import (
    CommandOutcome,
    require_profile_id,
    validate_limit,
)
from sightstalker.ids import new_profile_id
from sightstalker.models import ProfileId, ProfileRecord
from sightstalker.persistence import ProfileRepository, database_session
from sightstalker.sessions.paths import SessionPaths


def _profile_summary(config: CliRuntimeConfig, profile: ProfileRecord) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "profile_dir": safe_path_display(config, profile.profile_dir),
        "health_status": profile.health_status,
        "archived": profile.archived,
    }


def create_profile(
    config: CliRuntimeConfig,
    *,
    name: str,
    profile_id: str | None,
    profile_dir: str | None,
) -> CommandOutcome:
    """Create and persist a profile."""
    if name.strip() == "":
        raise CliUsageError("--name must not be empty")

    pid: ProfileId = (
        require_profile_id(profile_id)
        if profile_id is not None and profile_id != ""
        else new_profile_id()
    )

    paths = SessionPaths(config.data_dir)
    authority_dir = paths.profile_dir(pid)

    if profile_dir is not None and profile_dir != "":
        candidate = Path(profile_dir).expanduser().resolve()
        if candidate != authority_dir.resolve():
            raise CliUsageError(
                "--profile-dir must equal the SessionPaths authority "
                "for this profile id; arbitrary directories are not supported"
            )
        resolved_dir = authority_dir
    else:
        resolved_dir = authority_dir

    record = ProfileRecord(profile_id=pid, name=name, profile_dir=resolved_dir)

    async def _impl() -> ProfileRecord:
        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                async with session.begin():
                    repo = ProfileRepository(session, data_dir=config.data_dir)
                    return await repo.create(record)

    created = asyncio.run(_impl())
    summary = _profile_summary(config, created)

    def human(console: Console) -> None:
        console.print(f"Created profile [bold]{created.profile_id}[/bold]")
        console.print(f"  name: {created.name}")
        console.print(f"  dir:  {summary['profile_dir']}")

    return CommandOutcome(data=summary, human=human)


def list_profiles(
    config: CliRuntimeConfig,
    *,
    include_archived: bool,
    limit: int | None,
) -> CommandOutcome:
    """List profiles in deterministic repository order."""
    checked_limit = validate_limit(limit)

    async def _impl() -> list[ProfileRecord]:
        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                repo = ProfileRepository(session, data_dir=config.data_dir)
                return await repo.list(
                    include_archived=include_archived, limit=checked_limit
                )

    profiles = asyncio.run(_impl())
    rows = [_profile_summary(config, p) for p in profiles]

    def human(console: Console) -> None:
        if not rows:
            console.print("No profiles found.")
            return
        table = Table(title="Profiles")
        table.add_column("profile_id")
        table.add_column("name")
        table.add_column("dir")
        table.add_column("health")
        table.add_column("archived")
        for row in rows:
            table.add_row(
                str(row["profile_id"]),
                str(row["name"]),
                str(row["profile_dir"]),
                str(row["health_status"]),
                str(row["archived"]),
            )
        console.print(table)

    return CommandOutcome(data=rows, human=human)


def archive_profile(config: CliRuntimeConfig, *, profile_id: str) -> CommandOutcome:
    """Archive a profile (no file or row deletion, no cascade)."""
    pid = require_profile_id(profile_id)

    async def _impl() -> ProfileRecord:
        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                async with session.begin():
                    repo = ProfileRepository(session, data_dir=config.data_dir)
                    return await repo.archive(pid)

    archived = asyncio.run(_impl())
    summary = _profile_summary(config, archived)

    def human(console: Console) -> None:
        console.print(f"Archived profile [bold]{archived.profile_id}[/bold]")

    return CommandOutcome(data=summary, human=human)


__all__ = ["archive_profile", "create_profile", "list_profiles"]
