"""Public CLI behavior-equivalence tests for the ops boundary (§14.11).

These exercise the run/diag commands end-to-end through the CLI (which now
routes managed execution through ops) and assert that the public JSON envelope,
stable error labels, orphan-warning behavior, and redaction are unchanged.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.cli.main import app
from tests.cli.conftest import FakeEngine


def _engine_factory(engine: FakeEngine) -> Any:
    def make(name: str) -> FakeEngine:
        return engine

    return make


def _args(config: CliRuntimeConfig) -> list[str]:
    return ["--data-dir", str(config.data_dir), "--database-url", config.database_url]


def _make_session(runner: CliRunner, config: CliRuntimeConfig) -> str:
    args = _args(config)
    prof = runner.invoke(app, ["profile", "create", "--name", "p", "--json", *args])
    pid = json.loads(prof.stdout)["data"]["profile_id"]
    sess = runner.invoke(
        app,
        ["session", "create", "--name", "s", "--profile-id", pid, "--json", *args],
    )
    return cast(str, json.loads(sess.stdout)["data"]["session_id"])


def test_run_open_success_envelope(
    runner: CliRunner,
    initialized_config: CliRuntimeConfig,
    patch_engine: FakeEngine,
) -> None:
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid,
         "--url", "https://example.com/?api_key=raw-token-123",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    data = payload["data"]
    for key in ("run_id", "session_id", "status", "url", "final_url", "title"):
        assert key in data
    # Redacted URL only; raw token never present.
    assert "raw-token-123" not in result.stdout


def test_duplicate_navigation_emits_public_security_error(
    runner: CliRunner,
    initialized_config: CliRuntimeConfig,
    monkeypatch: pytest.MonkeyPatch,
    fake_engine: FakeEngine,
) -> None:
    # A plan that navigates twice must surface as public SecurityError.
    from sightstalker.ops import PlanResult, RunSurface

    async def double_nav_plan(surface: RunSurface) -> PlanResult:
        page = await surface.new_page()
        await surface.navigate(page)
        await surface.navigate(page)  # second navigation -> SecurityRefusal
        return PlanResult()

    monkeypatch.setattr(
        "sightstalker.cli.runs._run_open_plan", double_nav_plan
    )
    monkeypatch.setattr(
        "sightstalker.cli.runtime.create_engine_for_name",
        _engine_factory(fake_engine),
    )
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid, "--url", "https://example.com/",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code == 6
    entry = json.loads(result.stdout)["errors"][0]
    assert entry["type"] == "SecurityError"


def test_metadata_persistence_failure_emits_persistence_error_and_orphan_warning(
    runner: CliRunner,
    initialized_config: CliRuntimeConfig,
    monkeypatch: pytest.MonkeyPatch,
    fake_engine: FakeEngine,
) -> None:
    async def failing_create(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr("sightstalker.ops.runs.RunRepository.create", failing_create)
    monkeypatch.setattr(
        "sightstalker.cli.runtime.create_engine_for_name",
        _engine_factory(fake_engine),
    )
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["run", "open", "--session-id", sid, "--url", "about:blank",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["errors"][0]["type"] == "PersistenceError"
    assert any("metadata" in w for w in payload["warnings"])


def test_diag_screenshot_success_envelope(
    runner: CliRunner,
    initialized_config: CliRuntimeConfig,
    patch_engine: FakeEngine,
) -> None:
    sid = _make_session(runner, initialized_config)
    result = runner.invoke(
        app,
        ["diag", "screenshot", "--session-id", sid,
         "--url", "data:text/html,<title>ok</title>",
         "--json", *_args(initialized_config)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "screenshot" in payload["data"]
