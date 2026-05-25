"""Shared fixtures and a protocol-compliant fake engine for CLI tests.

The fake engine never imports Camoufox/Playwright. Its page/context support the
minimal surfaces the diagnostics services need (screenshot writes bytes, trace
stop writes bytes, native page supports console listener management).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from sightstalker.cli import db as db_cmds
from sightstalker.cli import profiles as profile_cmds
from sightstalker.cli import sessions as session_cmds
from sightstalker.cli.config import CliRuntimeConfig, resolve_config
from sightstalker.models import BrowserContextConfig, BrowserState, ContextId


class FakeConsoleMessage:
    def __init__(self, text: str) -> None:
        self.type = "log"
        self.text = text
        self.location = {"url": "about:blank", "lineNumber": 1}


class FakeNativePage:
    """Minimal native page supporting console listener management."""

    def __init__(self) -> None:
        self._listeners: list[Any] = []

    def on(self, event: str, callback: Any) -> None:
        if event == "console":
            self._listeners.append(callback)

    def remove_listener(self, event: str, callback: Any) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def emit_console(self, text: str) -> None:
        for cb in list(self._listeners):
            cb(FakeConsoleMessage(text))


class FakePage:
    def __init__(self) -> None:
        self.goto_calls = 0
        self.goto_urls: list[str] = []
        self._native = FakeNativePage()

    @property
    def native_page(self) -> Any:
        return self._native

    async def goto(
        self, url: str, *, wait_until: str = "load", timeout_ms: int | None = None
    ) -> None:
        self.goto_calls += 1
        self.goto_urls.append(url)
        # Emit a token-bearing console line to exercise console redaction.
        self._native.emit_console("hello access_token=raw-token-123")

    async def title(self) -> str:
        return "Fake Page\x07 Title"

    async def url(self) -> str:
        return "https://example.com/landing?api_key=raw-token-123"

    async def screenshot(
        self, *, path: str, full_page: bool = False, timeout_ms: int | None = None
    ) -> None:
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    async def close(self) -> None:
        return None


class FakeContext:
    def __init__(self, context_id: ContextId | None) -> None:
        self._context_id = context_id or cast(ContextId, "ctx_fake_00000000")
        self.closed = False
        self.tracing = False
        self.pages: list[FakePage] = []

    @property
    def context_id(self) -> ContextId:
        return self._context_id

    @property
    def native_context(self) -> Any:
        return None

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    async def storage_state(self) -> BrowserState:
        return BrowserState(engine_name="mock")

    async def start_tracing(self, *, name: str | None = None) -> None:
        self.tracing = True

    async def stop_tracing(self, *, path: str) -> None:
        Path(path).write_bytes(b"PK\x03\x04FAKE-TRACE")
        self.tracing = False

    async def close(self) -> None:
        self.closed = True


class FakeRuntime:
    def __init__(self) -> None:
        self.closed = False
        self.launch_config: Any = None
        self.contexts: list[FakeContext] = []

    @property
    def engine_name(self) -> str:
        return "mock"

    @property
    def native_browser(self) -> Any:
        return None

    async def new_context(
        self,
        config: BrowserContextConfig,
        *,
        initial_state: BrowserState | None = None,
        context_id: ContextId | None = None,
    ) -> FakeContext:
        ctx = FakeContext(context_id)
        self.contexts.append(ctx)
        return ctx

    async def close(self) -> None:
        self.closed = True


class FakeEngine:
    """Protocol-compliant fake browser engine (no browser package)."""

    def __init__(self) -> None:
        self.launch_calls = 0
        self.last_mode: str | None = None
        self.runtime = FakeRuntime()

    @property
    def name(self) -> str:
        return "mock"

    async def launch(self, config: Any) -> FakeRuntime:
        self.launch_calls += 1
        self.last_mode = config.mode
        self.runtime.launch_config = config
        return self.runtime

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A fresh, not-yet-created data directory path."""
    return tmp_path / "data"


@pytest.fixture
def initialized_db_dir(data_dir: Path) -> Path:
    """A data directory whose metadata database has been migrated to head."""
    config = resolve_config(
        data_dir=str(data_dir),
        database_url=None,
        json_output=False,
        verbose=False,
    )
    db_cmds.init_database(config)
    return data_dir


@pytest.fixture
def cli_config(tmp_path: Path) -> CliRuntimeConfig:
    data_dir = tmp_path / "data"
    db_path = data_dir / "metadata" / "sightstalker.sqlite3"
    return resolve_config(
        data_dir=str(data_dir),
        database_url=f"sqlite+aiosqlite:///{db_path}",
        json_output=False,
        verbose=False,
    )


@pytest.fixture
def initialized_config(cli_config: CliRuntimeConfig) -> CliRuntimeConfig:
    db_cmds.init_database(cli_config)
    return cli_config


@pytest.fixture
def profile_and_session(
    initialized_config: CliRuntimeConfig,
) -> tuple[CliRuntimeConfig, str, str]:
    profile = profile_cmds.create_profile(
        initialized_config, name="cli-test", profile_id=None, profile_dir=None
    )
    pid = cast(dict[str, Any], profile.data)["profile_id"]
    session = session_cmds.create_session(
        initialized_config,
        name="cli-test-session",
        profile_id=pid,
        session_id=None,
        engine="camoufox",
        headed=False,
    )
    sid = cast(dict[str, Any], session.data)["session_id"]
    return initialized_config, pid, sid


def cli_base(config: CliRuntimeConfig) -> list[str]:
    """Global args targeting the fixture's data dir and database."""
    return [
        "--data-dir",
        str(config.data_dir),
        "--database-url",
        config.database_url,
    ]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def patch_engine(monkeypatch: pytest.MonkeyPatch, fake_engine: FakeEngine) -> FakeEngine:
    """Monkeypatch the lazy engine factory to return the fake engine."""

    def factory(engine_name: str) -> FakeEngine:
        return fake_engine

    monkeypatch.setattr(
        "sightstalker.cli.runtime.create_engine_for_name", factory
    )
    return fake_engine
