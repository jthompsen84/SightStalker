"""``run open`` orchestration tests (fake engine; no real browser)."""

from __future__ import annotations

from typing import Any, cast

import pytest

from sightstalker.cli import runs as run_cmds
from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.redaction import prepare_navigation_url
from sightstalker.cli.types import CommandOutcome
from sightstalker.ops import RunSurface
from sightstalker.ops.errors import OpsPersistenceFailure
from sightstalker.resilience.errors import SecurityRefusal
from sightstalker.diagnostics import (
    DiagnosticArtifactRecorder,
    DiagnosticTarget,
)
from sightstalker.artifacts import ArtifactManager, ArtifactPaths

from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(engine_name: str) -> FakeEngine:
        return engine

    return make


def _run(
    config: CliRuntimeConfig,
    sid: str,
    url: str,
    engine: FakeEngine,
    *,
    headed_override: bool | None = None,
    timeout_ms: int | None = None,
) -> CommandOutcome:
    return run_cmds.run_open(
        config,
        session_id=sid,
        url=url,
        headed_override=headed_override,
        timeout_ms=timeout_ms,
        engine_factory=_factory(engine),
    )


def test_run_open_navigates_exactly_once(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    outcome = _run(config, sid, "https://example.com/", fake_engine)
    data = cast(dict[str, Any], outcome.data)
    assert data["status"] == "succeeded"

    context = fake_engine.runtime.contexts[0]
    pages = context.pages
    total_goto = sum(p.goto_calls for p in pages)
    assert total_goto == 1


def test_run_open_uses_raw_url_for_goto_but_persists_redacted(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    url = "https://example.com/?token=raw-token-123"
    outcome = _run(config, sid, url, fake_engine)
    data = cast(dict[str, Any], outcome.data)

    # Raw secret-bearing URL was used for navigation in-memory only.
    page = fake_engine.runtime.contexts[0].pages[0]
    assert page.goto_urls[0] == url
    # Persisted/output metadata URL is redacted.
    assert "raw-token-123" not in str(data["url"])
    assert "raw-token-123" not in str(data["final_url"])


def test_run_open_headed_override_changes_launch_mode(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    _run(config, sid, "about:blank", fake_engine, headed_override=True)
    assert fake_engine.last_mode == "headed"


def test_run_open_headless_default_mode(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    _run(config, sid, "about:blank", fake_engine)
    assert fake_engine.last_mode == "headless"


def test_run_open_validates_config_before_launch(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    fake_engine: FakeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _pid, sid = profile_and_session

    def boom(_cfg: Any) -> Any:
        raise ValueError("unsafe config")

    monkeypatch.setattr("sightstalker.ops.runs.persistable_session_config", boom)
    with pytest.raises(SecurityRefusal):
        _run(config, sid, "https://example.com/", fake_engine)
    # The browser must never launch when config validation fails.
    assert fake_engine.launch_calls == 0


def test_run_open_db_failure_keeps_artifacts_and_warns(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    fake_engine: FakeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _pid, sid = profile_and_session

    async def failing_create(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(
        "sightstalker.ops.runs.RunRepository.create", failing_create
    )
    with pytest.raises(OpsPersistenceFailure) as excinfo:
        _run(config, sid, "https://example.com/", fake_engine)
    assert excinfo.value.warnings  # orphan warning present
    assert "metadata" in excinfo.value.warnings[0]

    # Storage-state files were written and were NOT deleted.
    runs_root = config.data_dir / "profiles"
    state_files = list(runs_root.rglob("storage_state.final.json"))
    assert state_files, "final storage-state artifact should remain on disk"


def test_run_surface_rejects_second_navigation(tmp_path: Any) -> None:
    recorder = DiagnosticArtifactRecorder(ArtifactManager(ArtifactPaths(tmp_path)))
    surface = RunSurface(
        managed=cast(Any, None),
        raw_navigation_url="https://example.com/",
        recorder=recorder,
        base_target=DiagnosticTarget(),
    )

    class _P:
        async def goto(self, url: str, **k: Any) -> None:
            return None

    import asyncio

    page = cast(Any, _P())
    asyncio.run(surface.navigate(page))
    with pytest.raises(SecurityRefusal):
        asyncio.run(surface.navigate(page))


def test_prepare_navigation_url_round_trip() -> None:
    raw, meta = prepare_navigation_url("https://h/p?session=abc#access_token=xyz")
    assert raw.startswith("https://h/p")
    assert "abc" not in meta or "<redacted>" in meta
