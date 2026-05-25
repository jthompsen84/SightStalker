"""``diag console`` orchestration tests."""

from __future__ import annotations

from typing import Any, cast

from sightstalker.cli import diagnostics as diag_cmds
from sightstalker.cli.config import CliRuntimeConfig

from tests.cli.conftest import FakeEngine


def _factory(engine: FakeEngine) -> Any:
    def make(engine_name: str) -> FakeEngine:
        return engine

    return make


def test_diag_console_captures_redacted_run_log(
    profile_and_session: tuple[CliRuntimeConfig, str, str], fake_engine: FakeEngine
) -> None:
    config, _pid, sid = profile_and_session
    outcome = diag_cmds.diag_console(
        config,
        session_id=sid,
        url="about:blank",
        headed_override=None,
        timeout_ms=None,
        engine_factory=_factory(fake_engine),
    )
    data = cast(dict[str, Any], outcome.data)
    assert data["status"] == "succeeded"
    console = cast(dict[str, Any], data["console"])
    assert console["artifact_type"] == "run_log"

    # The fake page emits a token-bearing console line on goto; the persisted
    # JSONL artifact must not contain the raw token.
    artifact_path = config.data_dir / console["relative_path"]
    assert artifact_path.exists()
    text = artifact_path.read_text(encoding="utf-8")
    assert "raw-token-123" not in text
