"""``diag screenshot`` orchestration tests."""

from __future__ import annotations

from typing import Any, cast

from sightstalker.cli import diagnostics as diag_cmds
from sightstalker.cli.config import CliRuntimeConfig

from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(engine_name: str) -> FakeEngine:
        return engine

    return make


def test_diag_screenshot_captures_artifact(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    outcome = diag_cmds.diag_screenshot(
        config,
        session_id=sid,
        url="data:text/html,<title>ok</title>",
        headed_override=None,
        timeout_ms=None,
        engine_factory=_factory(fake_engine),
    )
    data = cast(dict[str, Any], outcome.data)
    assert data["status"] == "succeeded"
    shot = cast(dict[str, Any], data["screenshot"])
    assert shot["artifact_type"] == "screenshot"
    assert shot["size_bytes"] > 0
    # data: body is redacted in the output URL.
    assert data["url"] == "data:text/html,<redacted>"

    # The screenshot artifact file exists on disk under the data dir.
    rel = shot["relative_path"]
    assert (config.data_dir / rel).exists()


def test_diag_screenshot_navigates_once(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    diag_cmds.diag_screenshot(
        config,
        session_id=sid,
        url="about:blank",
        headed_override=None,
        timeout_ms=None,
        engine_factory=_factory(fake_engine),
    )
    context = fake_engine.runtime.contexts[0]
    total_goto = sum(p.goto_calls for p in context.pages)
    assert total_goto == 1
