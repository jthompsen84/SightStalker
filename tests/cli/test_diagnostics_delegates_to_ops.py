"""``cli.diagnostics`` commands must delegate managed execution to ops."""

from __future__ import annotations

from typing import Any, cast

import pytest

from sightstalker.cli import diagnostics as diag_cmds
from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.ops import ManagedRunResult


def _patch_execute(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
) -> None:
    async def fake_execute(**kwargs: Any) -> ManagedRunResult:
        captured.update(kwargs)
        return ManagedRunResult(
            data={
                "run_id": "run_x",
                "status": "succeeded",
                "url": "about:blank",
                "final_url": None,
                "title": None,
                "artifact_count": 0,
            }
        )

    monkeypatch.setattr(diag_cmds, "execute_managed_run", fake_execute)


def _factory(name: str) -> Any:
    return object()


def _invoke_diag(
    kind: str, config: CliRuntimeConfig, sid: str, factory: Any
) -> None:
    common: dict[str, Any] = {
        "session_id": sid,
        "url": "data:text/html,<title>ok</title>",
        "headed_override": None,
        "timeout_ms": None,
        "engine_factory": factory,
    }
    if kind == "screenshot":
        diag_cmds.diag_screenshot(config, **common)
    elif kind == "trace":
        diag_cmds.diag_trace(config, **common)
    else:
        diag_cmds.diag_console(config, **common)


@pytest.mark.parametrize("kind", ["screenshot", "trace", "console"])
def test_diag_command_delegates_to_ops(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    config, _pid, sid = profile_and_session
    captured: dict[str, Any] = {}
    _patch_execute(monkeypatch, captured)

    _invoke_diag(kind, config, sid, cast(Any, _factory))

    # Delegated with ops input shape, not CliRuntimeConfig.
    assert "config" not in captured
    assert captured["data_dir"] == config.data_dir
    assert captured["session_factory"] is not None
    assert captured["session_id"] == sid
    assert callable(captured["plan"])


def test_diag_plans_remain_in_cli_diagnostics() -> None:
    # Concrete diagnostic plans stay in cli.diagnostics, not ops.
    assert hasattr(diag_cmds, "_screenshot_plan")
    assert hasattr(diag_cmds, "_trace_plan")
    assert hasattr(diag_cmds, "_console_plan")
