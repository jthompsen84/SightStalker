"""``diag trace`` orchestration tests."""

from __future__ import annotations

from typing import Any, cast

from sightstalker.cli import diagnostics as diag_cmds
from sightstalker.cli.config import CliRuntimeConfig

from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(engine_name: str) -> FakeEngine:
        return engine

    return make


def test_diag_trace_starts_before_navigation_and_captures(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    outcome = diag_cmds.diag_trace(
        config,
        session_id=sid,
        url="about:blank",
        headed_override=None,
        timeout_ms=None,
        engine_factory=_factory(fake_engine),
    )
    data = cast(dict[str, Any], outcome.data)
    assert data["status"] == "succeeded"
    trace = cast(dict[str, Any], data["trace"])
    assert trace["artifact_type"] == "trace"
    assert trace["size_bytes"] > 0
    assert (config.data_dir / trace["relative_path"]).exists()

    context = fake_engine.runtime.contexts[0]
    total_goto = sum(p.goto_calls for p in context.pages)
    assert total_goto == 1
