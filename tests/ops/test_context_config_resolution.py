# pyright: reportPrivateUsage=false
"""Tests that ops invokes the resolver before launch and preserves defaults."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.context import cli_persistence
from sightstalker.environment.models import (
    ContextConfigResolution,
    LaunchConfigOverrides,
    RunConfigOverrides,
)
from sightstalker.environment.resolver import DefaultContextConfigResolver
from sightstalker.ops import ManagedRunResult, PlanResult, RunSurface, execute_managed_run
from sightstalker.ops.runs import _normalize_mode_overrides
from sightstalker.resilience.errors import UsageError
from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(name: str) -> FakeEngine:
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
    headed_override: bool | None = None,
    resolver: Any = None,
    overrides: Any = None,
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
                headed_override=headed_override,
                timeout_ms=None,
                plan=_plan,
                context_config_resolver=resolver,
                run_config_overrides=overrides,
            )

    return asyncio.run(_impl())


def test_no_resolver_preserves_default_behavior(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    result = _run(config, sid, fake_engine)
    assert result.data["status"] == "succeeded"


def test_no_resolver_headed_override_applies_via_apply_mode_override(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    _run(config, sid, fake_engine, headed_override=True)
    assert fake_engine.last_mode == "headed"


def test_resolver_invoked_before_engine_factory(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    order: list[str] = []

    class _TrackingResolver:
        async def resolve(self, **kwargs: Any) -> ContextConfigResolution:
            order.append("resolve")
            session = kwargs["session"]
            return ContextConfigResolution(
                launch=session.config.launch, context=session.config.context
            )

    def tracking_factory(name: str) -> FakeEngine:
        order.append("engine_factory")
        return fake_engine

    async def _impl() -> ManagedRunResult:
        async with cli_persistence(config) as factory:
            return await execute_managed_run(
                data_dir=config.data_dir,
                session_factory=factory,
                engine_factory=cast(Any, tracking_factory),
                session_id=cast(Any, sid),
                raw_navigation_url="https://example.com/",
                metadata_url_redacted="https://example.com/",
                headed_override=None,
                timeout_ms=None,
                plan=_plan,
                context_config_resolver=cast(Any, _TrackingResolver()),
            )

    asyncio.run(_impl())
    assert order == ["resolve", "engine_factory"]


def test_resolver_branch_headed_override_yields_headed_mode(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    resolver = DefaultContextConfigResolver()
    _run(config, sid, fake_engine, headed_override=True, resolver=resolver)
    assert fake_engine.last_mode == "headed"


def test_conflicting_mode_raises_usage_error_before_engine_factory(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    engine_built = {"n": 0}

    def counting_factory(name: str) -> FakeEngine:
        engine_built["n"] += 1
        return fake_engine

    overrides = RunConfigOverrides(launch=LaunchConfigOverrides(mode="headless"))

    async def _impl() -> ManagedRunResult:
        async with cli_persistence(config) as factory:
            return await execute_managed_run(
                data_dir=config.data_dir,
                session_factory=factory,
                engine_factory=cast(Any, counting_factory),
                session_id=cast(Any, sid),
                raw_navigation_url="https://example.com/",
                metadata_url_redacted="https://example.com/",
                headed_override=True,  # conflicts with headless override
                timeout_ms=None,
                plan=_plan,
                context_config_resolver=DefaultContextConfigResolver(),
                run_config_overrides=overrides,
            )

    with pytest.raises(UsageError):
        asyncio.run(_impl())
    assert engine_built["n"] == 0


def test_run_overrides_without_resolver_raise_usage_error(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    overrides = RunConfigOverrides(launch=LaunchConfigOverrides(mode="headed"))
    with pytest.raises(UsageError):
        _run(config, sid, fake_engine, overrides=overrides)


# --- _normalize_mode_overrides unit tests ----------------------------------


def test_normalize_none_headed_passthrough() -> None:
    assert _normalize_mode_overrides(None, None) is None


def test_normalize_headed_true_creates_headed_override() -> None:
    result = _normalize_mode_overrides(True, None)
    assert result is not None and result.launch is not None
    assert result.launch.mode == "headed"


def test_normalize_agreeing_modes_ok() -> None:
    overrides = RunConfigOverrides(launch=LaunchConfigOverrides(mode="headed"))
    result = _normalize_mode_overrides(True, overrides)
    assert result is not None and result.launch is not None
    assert result.launch.mode == "headed"


def test_normalize_conflicting_modes_raises() -> None:
    overrides = RunConfigOverrides(launch=LaunchConfigOverrides(mode="headless"))
    with pytest.raises(UsageError):
        _normalize_mode_overrides(True, overrides)
