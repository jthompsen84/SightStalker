"""Tests for sightstalker.ops.runs.execute_managed_run (fakes; no browser)."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.context import cli_persistence
from sightstalker.ops import ManagedRunResult, PlanResult, RunSurface, execute_managed_run
from sightstalker.ops.errors import OpsPersistenceFailure
from sightstalker.resilience.errors import BrowserRuntimeError, SecurityRefusal
from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(engine_name: str) -> FakeEngine:
        return engine

    return make


async def _open_plan(surface: RunSurface) -> PlanResult:
    page = await surface.new_page()
    await surface.navigate(page)
    title = await page.title()
    final_url = await page.url()
    return PlanResult(title=title, final_url=final_url)


def _run(
    config: CliRuntimeConfig,
    sid: str,
    engine: FakeEngine,
    *,
    url: str = "https://example.com/?api_key=raw-token-123",
    headed_override: bool | None = None,
    plan: Any = None,
) -> ManagedRunResult:
    async def _impl() -> ManagedRunResult:
        async with cli_persistence(config) as factory:
            return await execute_managed_run(
                data_dir=config.data_dir,
                session_factory=factory,
                engine_factory=_factory(engine),
                session_id=cast(Any, sid),
                raw_navigation_url=url,
                metadata_url_redacted="https://example.com/?api_key=<redacted>",
                headed_override=headed_override,
                timeout_ms=None,
                plan=plan if plan is not None else _open_plan,
            )

    return asyncio.run(_impl())


def test_returns_managed_run_result(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    result = _run(config, sid, fake_engine)
    assert isinstance(result, ManagedRunResult)
    assert result.data["status"] == "succeeded"


def test_loads_session_and_opens_one_context(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    _run(config, sid, fake_engine)
    assert fake_engine.launch_calls == 1
    assert len(fake_engine.runtime.contexts) == 1


def test_plan_called_once(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    calls = {"n": 0}

    async def counting_plan(surface: RunSurface) -> PlanResult:
        calls["n"] += 1
        page = await surface.new_page()
        await surface.navigate(page)
        return PlanResult()

    _run(config, sid, fake_engine, plan=counting_plan)
    assert calls["n"] == 1


def test_validates_config_before_launch(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    fake_engine: FakeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _pid, sid = profile_and_session

    def boom(_cfg: Any) -> Any:
        raise ValueError("unsafe config")

    monkeypatch.setattr("sightstalker.ops.runs.persistable_session_config", boom)
    with pytest.raises(SecurityRefusal):
        _run(config, sid, fake_engine)
    assert fake_engine.launch_calls == 0


def test_headed_override_changes_effective_launch_mode(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    _run(config, sid, fake_engine, headed_override=True)
    assert fake_engine.last_mode == "headed"


def test_headless_override_changes_effective_launch_mode(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    _run(config, sid, fake_engine, headed_override=False)
    assert fake_engine.last_mode == "headless"


def test_stored_session_config_not_mutated_by_override(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    # The session was created headless; a headed override must not persist back.
    _run(config, sid, fake_engine, headed_override=True)

    async def _read_mode() -> str:
        from sightstalker.persistence import SessionRepository, database_session

        async with cli_persistence(config) as factory:
            async with database_session(factory) as session:
                repo = SessionRepository(session)
                record = await repo.require(cast(Any, sid))
                return record.config.launch.mode

    assert asyncio.run(_read_mode()) == "headless"


def test_engine_factory_receives_engine_name(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    seen: dict[str, Any] = {}

    def make(engine_name: str) -> FakeEngine:
        seen["name"] = engine_name
        return fake_engine

    async def _impl() -> ManagedRunResult:
        async with cli_persistence(config) as factory:
            return await execute_managed_run(
                data_dir=config.data_dir,
                session_factory=factory,
                engine_factory=cast(Any, make),
                session_id=cast(Any, sid),
                raw_navigation_url="about:blank",
                metadata_url_redacted="about:blank",
                headed_override=None,
                timeout_ms=None,
                plan=_open_plan,
            )

    asyncio.run(_impl())
    assert seen["name"] == "camoufox"


def test_metadata_url_redacted_raw_not_persisted(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    result = _run(config, sid, fake_engine)
    blob = str(result.data)
    assert "raw-token-123" not in blob
    assert result.data["url"] == "https://example.com/?api_key=<redacted>"


def test_non_project_plan_error_becomes_browser_failure(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def bad_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        raise RuntimeError("plan blew up")

    with pytest.raises(BrowserRuntimeError):
        _run(config, sid, fake_engine, plan=bad_plan)


def test_project_plan_error_is_preserved(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def refusing_plan(surface: RunSurface) -> PlanResult:
        raise SecurityRefusal("plan refused")

    with pytest.raises(SecurityRefusal):
        _run(config, sid, fake_engine, plan=refusing_plan)


def test_db_failure_preserves_orphan_warning_and_files(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    fake_engine: FakeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _pid, sid = profile_and_session

    async def failing_create(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr("sightstalker.ops.runs.RunRepository.create", failing_create)
    with pytest.raises(OpsPersistenceFailure) as excinfo:
        _run(config, sid, fake_engine)
    assert excinfo.value.warnings
    assert "metadata" in excinfo.value.warnings[0]
    # Storage-state files remain on disk (not deleted).
    state_files = list((config.data_dir / "profiles").rglob("storage_state.final.json"))
    assert state_files


def test_successful_run_persists_artifacts(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    result = _run(config, sid, fake_engine)
    assert cast(int, result.data["artifact_count"]) >= 2


# --- PlanResult.extra safety floor (spec 9.6 / 14.12) ---------------------


def test_extra_token_like_value_sanitized(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def leaky_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        return PlanResult(extra={"note": "access_token=raw-token-123"})

    result = _run(config, sid, fake_engine, plan=leaky_plan)
    assert "raw-token-123" not in str(result.data)


def test_extra_data_url_value_sanitized(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def leaky_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        return PlanResult(extra={"u": "db url sqlite+aiosqlite://user:secret@host"})

    result = _run(config, sid, fake_engine, plan=leaky_plan)
    assert "user:secret" not in str(result.data)


def test_extra_non_json_value_rejected(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def bad_extra_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        result = PlanResult()
        # Bypass typing to inject a non-JSON object.
        result.extra = cast(Any, {"obj": object()})
        return result

    with pytest.raises(BrowserRuntimeError):
        _run(config, sid, fake_engine, plan=bad_extra_plan)


def test_safe_extra_values_preserved(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session

    async def safe_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        return PlanResult(extra={"count": 3, "ok": True, "label": "plain"})

    result = _run(config, sid, fake_engine, plan=safe_plan)
    assert result.data["count"] == 3
    assert result.data["ok"] is True
    assert result.data["label"] == "plain"
