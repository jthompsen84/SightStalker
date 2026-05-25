"""
sightstalker.cli.runs — the ``run open`` command.

As of v0.4.2 the shared managed-run orchestration lives in ``sightstalker.ops``.
This module owns only the run-open command: CLI input preparation (URL split,
id/timeout validation), the run-open-specific plan, delegation to
``ops.execute_managed_run``, and human/JSON rendering via ``CommandOutcome``.

Raw navigation URLs and ``data:`` bodies are never persisted or printed; the CLI
splits the raw URL (in-memory ``page.goto`` only) from the redacted metadata URL
(persisted/printed) before entering ops.
"""

from __future__ import annotations

import asyncio

from rich.console import Console

from sightstalker.cli import runtime as cli_runtime
from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.context import cli_persistence
from sightstalker.cli.redaction import prepare_navigation_url
from sightstalker.cli.types import (
    CommandOutcome,
    require_session_id,
    validate_timeout_ms,
)
from sightstalker.ops import (
    EngineFactory,
    ManagedRunResult,
    PlanResult,
    RunSurface,
    execute_managed_run,
)


async def _run_open_plan(surface: RunSurface) -> PlanResult:
    page = await surface.new_page()
    await surface.navigate(page)
    title = await page.title()
    final_url = await page.url()
    return PlanResult(title=title, final_url=final_url)


def run_open(
    config: CliRuntimeConfig,
    *,
    session_id: str,
    url: str,
    headed_override: bool | None,
    timeout_ms: int | None,
    engine_factory: EngineFactory | None = None,
) -> CommandOutcome:
    """Open a session, navigate once to a URL, and record the run."""
    sid = require_session_id(session_id)
    raw_url, metadata_url = prepare_navigation_url(url)
    timeout = validate_timeout_ms(timeout_ms)
    effective_factory = (
        engine_factory
        if engine_factory is not None
        else cli_runtime.create_engine_for_name
    )

    async def _impl() -> ManagedRunResult:
        async with cli_persistence(config) as factory:
            return await execute_managed_run(
                data_dir=config.data_dir,
                session_factory=factory,
                engine_factory=effective_factory,
                session_id=sid,
                raw_navigation_url=raw_url,
                metadata_url_redacted=metadata_url,
                headed_override=headed_override,
                timeout_ms=timeout,
                plan=_run_open_plan,
            )

    result = asyncio.run(_impl())
    data = result.data

    def human(console: Console) -> None:
        console.print(f"Run [bold]{data['run_id']}[/bold] {data['status']}")
        console.print(f"  url:       {data['url']}")
        console.print(f"  final url: {data['final_url']}")
        console.print(f"  title:     {data['title']}")
        console.print(f"  artifacts: {data['artifact_count']}")

    return CommandOutcome(data=data, human=human, warnings=list(result.warnings))


__all__ = ["run_open"]
