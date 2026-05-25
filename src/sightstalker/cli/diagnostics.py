"""
sightstalker.cli.diagnostics — explicit one-shot diagnostic capture commands.

Each command opens one managed run, navigates exactly once, and uses the
accepted passive diagnostics services (screenshot / trace / console) to produce
an artifact, then persists run/context/storage/diagnostic metadata in one
transaction via the shared run executor. The diagnostics services stay passive:
they observe an already-open page/context and never navigate, retry, or close
the runtime.
"""

from __future__ import annotations

import asyncio
from typing import cast

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
    Plan,
    PlanResult,
    RunSurface,
    execute_managed_run,
)
from sightstalker.ops.plans import JsonObject
from sightstalker.diagnostics import (
    ConsoleCaptureService,
    ScreenshotOptions,
    ScreenshotService,
    TraceOptions,
    TraceService,
)
from sightstalker.models import ArtifactRef, SessionId

_DIAGNOSTIC_RUN_ORDER = 10


def _artifact_summary(ref: ArtifactRef) -> JsonObject:
    return {
        "artifact_id": ref.artifact_id,
        "artifact_type": ref.artifact_type,
        "relative_path": str(ref.relative_path),
        "size_bytes": ref.size_bytes,
        "sha256": ref.sha256,
    }


async def _screenshot_plan(surface: RunSurface) -> PlanResult:
    page = await surface.new_page()
    await surface.navigate(page)
    service = ScreenshotService(surface.recorder)
    result = await service.capture(
        page,
        target=surface.target_with_order(_DIAGNOSTIC_RUN_ORDER),
        options=ScreenshotOptions(),
        policy=None,
    )
    title = await page.title()
    final_url = await page.url()
    return PlanResult(
        title=title,
        final_url=final_url,
        diagnostics=[(result.artifact_ref, _DIAGNOSTIC_RUN_ORDER)],
        extra={"screenshot": _artifact_summary(result.artifact_ref)},
    )


async def _trace_plan(surface: RunSurface) -> PlanResult:
    service = TraceService(surface.recorder)
    handle = await service.start(
        surface.context,
        target=surface.target_with_order(_DIAGNOSTIC_RUN_ORDER),
        options=TraceOptions(),
    )
    page = await surface.new_page()
    await surface.navigate(page)
    result = await handle.stop(policy=None)
    title = await page.title()
    final_url = await page.url()
    return PlanResult(
        title=title,
        final_url=final_url,
        diagnostics=[(result.artifact_ref, _DIAGNOSTIC_RUN_ORDER)],
        extra={"trace": _artifact_summary(result.artifact_ref)},
    )


async def _console_plan(surface: RunSurface) -> PlanResult:
    page = await surface.new_page()
    service = ConsoleCaptureService(surface.recorder)
    handle = service.attach(page, target=surface.target_with_order(_DIAGNOSTIC_RUN_ORDER))
    await surface.navigate(page)
    result = await handle.write_artifact(policy=None)
    handle.detach()
    title = await page.title()
    final_url = await page.url()
    return PlanResult(
        title=title,
        final_url=final_url,
        diagnostics=[(result.artifact_ref, _DIAGNOSTIC_RUN_ORDER)],
        extra={
            "console": _artifact_summary(result.artifact_ref),
            "console_event_count": handle.event_count,
        },
    )


def _run_diagnostic(
    config: CliRuntimeConfig,
    *,
    kind: str,
    session_id: str,
    url: str,
    headed_override: bool | None,
    timeout_ms: int | None,
    plan: Plan,
    engine_factory: EngineFactory | None,
) -> CommandOutcome:
    sid: SessionId = require_session_id(session_id)
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
                plan=plan,
            )

    result = asyncio.run(_impl())
    data = result.data

    def human(console: Console) -> None:
        console.print(f"Diagnostic [bold]{kind}[/bold] captured for run {data['run_id']}")
        artifact = data.get(kind)
        if isinstance(artifact, dict):
            art = cast("dict[str, object]", artifact)
            console.print(f"  artifact: {art.get('artifact_id')}")
            console.print(f"  path:     {art.get('relative_path')}")
            console.print(f"  size:     {art.get('size_bytes')} bytes")

    return CommandOutcome(data=data, human=human, warnings=list(result.warnings))


def diag_screenshot(
    config: CliRuntimeConfig,
    *,
    session_id: str,
    url: str,
    headed_override: bool | None,
    timeout_ms: int | None,
    engine_factory: EngineFactory | None = None,
) -> CommandOutcome:
    return _run_diagnostic(
        config,
        kind="screenshot",
        session_id=session_id,
        url=url,
        headed_override=headed_override,
        timeout_ms=timeout_ms,
        plan=_screenshot_plan,
        engine_factory=engine_factory,
    )


def diag_trace(
    config: CliRuntimeConfig,
    *,
    session_id: str,
    url: str,
    headed_override: bool | None,
    timeout_ms: int | None,
    engine_factory: EngineFactory | None = None,
) -> CommandOutcome:
    return _run_diagnostic(
        config,
        kind="trace",
        session_id=session_id,
        url=url,
        headed_override=headed_override,
        timeout_ms=timeout_ms,
        plan=_trace_plan,
        engine_factory=engine_factory,
    )


def diag_console(
    config: CliRuntimeConfig,
    *,
    session_id: str,
    url: str,
    headed_override: bool | None,
    timeout_ms: int | None,
    engine_factory: EngineFactory | None = None,
) -> CommandOutcome:
    return _run_diagnostic(
        config,
        kind="console",
        session_id=session_id,
        url=url,
        headed_override=headed_override,
        timeout_ms=timeout_ms,
        plan=_console_plan,
        engine_factory=engine_factory,
    )


__all__ = ["diag_console", "diag_screenshot", "diag_trace"]
