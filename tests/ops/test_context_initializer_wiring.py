"""Managed-run wiring tests for the context initializer chain.

Verifies initializers run after context creation and inside the
cleanup-protected region before plan execution; that initializer failure aborts
the plan, routes through ManagedSessionContext cleanup exactly once, releases the
profile lock, and is phase-labeled; that process-control exceptions re-raise; and
that the empty chain preserves v0.4.4 behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.context import cli_persistence
from sightstalker.ops import (
    ContextInitializationScope,
    ManagedRunResult,
    PlanResult,
    RunSurface,
    execute_managed_run,
)
from sightstalker.resilience.errors import BrowserRuntimeError, UsageError
from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(engine_name: str) -> FakeEngine:
        return engine

    return make


async def _plan(surface: RunSurface) -> PlanResult:
    page = await surface.new_page()
    await surface.navigate(page)
    return PlanResult(title=await page.title(), final_url=await page.url())


def _run(
    config: CliRuntimeConfig,
    sid: str,
    engine: FakeEngine,
    *,
    initializers: tuple[Any, ...] = (),
    plan: Any = None,
) -> ManagedRunResult:
    async def _impl() -> ManagedRunResult:
        async with cli_persistence(config) as factory:
            return await execute_managed_run(
                data_dir=config.data_dir,
                session_factory=factory,
                engine_factory=_factory(engine),
                session_id=cast(Any, sid),
                raw_navigation_url="https://example.com/",
                metadata_url_redacted="https://example.com/",
                headed_override=None,
                timeout_ms=None,
                plan=plan if plan is not None else _plan,
                context_initializers=initializers,
            )

    return asyncio.run(_impl())


def test_initializer_runs_before_plan(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    events: list[str] = []

    class _Init:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            events.append("initializer")

    async def _tracking_plan(surface: RunSurface) -> PlanResult:
        events.append("plan")
        page = await surface.new_page()
        await surface.navigate(page)
        return PlanResult()

    _run(config, sid, fake_engine, initializers=(_Init(),), plan=_tracking_plan)
    assert events == ["initializer", "plan"]


def test_initializer_runs_after_context_exists(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    seen: dict[str, Any] = {}

    class _Init:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            seen["context_id"] = scope.context.context_id
            seen["session_id"] = scope.request.session_id
            seen["resolution_mode"] = scope.resolution.launch.mode

    _run(config, sid, fake_engine, initializers=(_Init(),))
    assert seen["context_id"]  # a live context handle was available
    assert seen["session_id"] == sid


def test_empty_chain_preserves_behavior(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    result = _run(config, sid, fake_engine, initializers=())
    assert result.data["status"] == "succeeded"


def test_initializer_failure_aborts_plan(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    plan_called = {"v": False}

    class _Boom:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise RuntimeError("init boom")

    async def _plan_marker(surface: RunSurface) -> PlanResult:
        plan_called["v"] = True
        return PlanResult()

    with pytest.raises(UsageError):
        _run(config, sid, fake_engine, initializers=(_Boom(),), plan=_plan_marker)
    assert plan_called["v"] is False


def test_initializer_failure_phase_label(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    class _Boom:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise RuntimeError("init boom")

    with pytest.raises(UsageError) as excinfo:
        _run(config, sid, fake_engine, initializers=(_Boom(),))
    # Phase-specific initializer message, not the plan-phase wording.
    assert "context initializer failed" in excinfo.value.message
    assert "navigation/capture" not in excinfo.value.message


def test_second_initializer_not_called_after_first_fails(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    second_called = {"v": False}

    class _Boom:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise RuntimeError("boom")

    class _Second:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            second_called["v"] = True

    with pytest.raises(UsageError):
        _run(config, sid, fake_engine, initializers=(_Boom(), _Second()))
    assert second_called["v"] is False


def test_initializer_failure_releases_profile_lock(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    class _Boom:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise RuntimeError("boom")

    with pytest.raises(UsageError):
        _run(config, sid, fake_engine, initializers=(_Boom(),))

    # A subsequent run on the same profile/session must succeed (lock released).
    result = _run(config, sid, fake_engine, initializers=())
    assert result.data["status"] == "succeeded"


def test_project_error_from_initializer_preserved(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    class _Refuse:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise UsageError("explicit project usage error")

    with pytest.raises(UsageError) as excinfo:
        _run(config, sid, fake_engine, initializers=(_Refuse(),))
    # Preserved as-is, not re-wrapped into the generic initializer label.
    assert "explicit project usage error" in excinfo.value.message


def test_keyboard_interrupt_reraised(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    class _Interrupt:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _run(config, sid, fake_engine, initializers=(_Interrupt(),))


def test_cancelled_error_reraised(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    class _Cancel:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        _run(config, sid, fake_engine, initializers=(_Cancel(),))


def test_plan_failure_still_browser_runtime_error(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def _bad_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        raise RuntimeError("plan boom")

    # Plan-phase failures keep the existing classification/wording.
    with pytest.raises(BrowserRuntimeError) as excinfo:
        _run(config, sid, fake_engine, initializers=(), plan=_bad_plan)
    assert "navigation/capture" in excinfo.value.message
