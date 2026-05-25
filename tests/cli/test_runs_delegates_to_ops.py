"""``cli.runs.run_open`` must delegate managed execution to ops."""

from __future__ import annotations

from typing import Any, cast

import pytest

from sightstalker.cli import runs as run_cmds
from sightstalker.cli.config import CliRuntimeConfig
from sightstalker.ops import ManagedRunResult


def _obj_factory(name: str) -> Any:
    return object()


def test_run_open_delegates_to_ops_execute_managed_run(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _pid, sid = profile_and_session
    captured: dict[str, Any] = {}

    async def fake_execute(**kwargs: Any) -> ManagedRunResult:
        captured.update(kwargs)
        return ManagedRunResult(data={"run_id": "run_x", "status": "succeeded",
                                       "url": "about:blank", "final_url": None,
                                       "title": None, "artifact_count": 0})

    # cli.runs imports execute_managed_run into its own namespace.
    monkeypatch.setattr(run_cmds, "execute_managed_run", fake_execute)

    def engine_factory(name: str) -> Any:
        return object()

    outcome = run_cmds.run_open(
        config,
        session_id=sid,
        url="https://example.com/?api_key=raw-token-123",
        headed_override=True,
        timeout_ms=12345,
        engine_factory=cast(Any, engine_factory),
    )

    assert isinstance(outcome.data, dict)
    # The ops executor received the expected delegated values.
    assert captured["data_dir"] == config.data_dir
    assert captured["session_factory"] is not None
    assert captured["engine_factory"] is engine_factory
    assert captured["session_id"] == sid
    assert captured["raw_navigation_url"] == "https://example.com/?api_key=raw-token-123"
    assert "raw-token-123" not in captured["metadata_url_redacted"]
    assert captured["headed_override"] is True
    assert captured["timeout_ms"] == 12345
    assert callable(captured["plan"])


def test_run_open_passes_data_dir_not_config(
    profile_and_session: tuple[CliRuntimeConfig, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _pid, sid = profile_and_session
    captured: dict[str, Any] = {}

    async def fake_execute(**kwargs: Any) -> ManagedRunResult:
        captured.update(kwargs)
        return ManagedRunResult(data={"run_id": "r", "status": "succeeded",
                                      "url": "about:blank", "final_url": None,
                                      "title": None, "artifact_count": 0})

    monkeypatch.setattr(run_cmds, "execute_managed_run", fake_execute)
    run_cmds.run_open(
        config,
        session_id=sid,
        url="about:blank",
        headed_override=None,
        timeout_ms=None,
        engine_factory=cast(Any, _obj_factory),
    )
    assert "config" not in captured
    assert captured["data_dir"] == config.data_dir
