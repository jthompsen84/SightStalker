"""Shared fixtures and fakes for diagnostics tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sightstalker.artifacts import ArtifactManager, ArtifactPaths
from sightstalker.diagnostics import (
    DiagnosticArtifactRecorder,
    DiagnosticTarget,
)


@pytest.fixture
def manager(tmp_path: Path) -> ArtifactManager:
    paths = ArtifactPaths(tmp_path / "data")
    paths.ensure_data_dir()
    return ArtifactManager(paths)


@pytest.fixture
def recorder(manager: ArtifactManager) -> DiagnosticArtifactRecorder:
    return DiagnosticArtifactRecorder(manager)


@pytest.fixture
def run_target() -> DiagnosticTarget:
    return DiagnosticTarget(
        session_id="sess_alpha_default",
        run_id="run_auto_0123456789abcdef",
        run_order=0,
    )


@pytest.fixture
def unscoped_target() -> DiagnosticTarget:
    return DiagnosticTarget()


# --- Fakes -----------------------------------------------------------------


class FakeNativePage:
    """Fake Python-Playwright-like native page for console capture."""

    def __init__(self) -> None:
        self._callback: Any = None
        self.removed = False

    def on(self, event: str, callback: Any) -> None:
        assert event == "console"
        self._callback = callback

    def remove_listener(self, event: str, callback: Any) -> None:
        assert event == "console"
        self.removed = True
        self._callback = None

    def emit(self, message: Any) -> None:
        if self._callback is not None:
            self._callback(message)


class FakeConsoleMessage:
    def __init__(self, msg_type: str, text: str, location: Any = None) -> None:
        self._type = msg_type
        self._text = text
        self._location = location

    @property
    def type(self) -> str:
        return self._type

    @property
    def text(self) -> str:
        return self._text

    @property
    def location(self) -> Any:
        return self._location


class FakePage:
    """Fake PageHandle that writes deterministic screenshot bytes."""

    def __init__(self, native: Any = None, *, fail: bool = False) -> None:
        self._native = native if native is not None else FakeNativePage()
        self._fail = fail
        self.screenshot_calls: list[dict[str, Any]] = []

    @property
    def native_page(self) -> Any:
        return self._native

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout_ms: int | None = None,
    ) -> None:
        raise AssertionError("diagnostics must not navigate")

    async def title(self) -> str:
        return ""

    async def url(self) -> str:
        return ""

    async def screenshot(
        self, *, path: str, full_page: bool = False, timeout_ms: int | None = None
    ) -> None:
        self.screenshot_calls.append(
            {"path": path, "full_page": full_page, "timeout_ms": timeout_ms}
        )
        if self._fail:
            raise RuntimeError("native screenshot boom")
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    async def close(self) -> None:
        raise AssertionError("diagnostics must not close pages")


class FakeContext:
    """Fake BrowserContextHandle for tracing."""

    def __init__(
        self, *, fail_start: bool = False, fail_stop: bool = False
    ) -> None:
        self._fail_start = fail_start
        self._fail_stop = fail_stop
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def context_id(self) -> str:
        return "ctx_fake_0123456789ab"

    @property
    def native_context(self) -> Any:
        return None

    async def new_page(self) -> Any:
        raise AssertionError("diagnostics must not create pages")

    async def storage_state(self) -> Any:
        raise AssertionError("diagnostics must not export storage state")

    async def start_tracing(self, *, name: str | None = None) -> None:
        self.start_calls += 1
        if self._fail_start:
            raise RuntimeError("native trace start boom")

    async def stop_tracing(self, *, path: str) -> None:
        self.stop_calls += 1
        if self._fail_stop:
            raise RuntimeError("native trace stop boom")
        Path(path).write_bytes(b"PK\x03\x04FAKEZIP")

    async def close(self) -> None:
        raise AssertionError("diagnostics must not close contexts")


class RecordingArtifactRepo:
    """In-memory repository-like artifact sink."""

    def __init__(self, *, fail: bool = False) -> None:
        self.created: list[dict[str, Any]] = []
        self._fail = fail

    async def create(
        self,
        ref: Any,
        *,
        session_id: Any = None,
        run_id: Any = None,
        run_order: Any = None,
    ) -> Any:
        if self._fail:
            raise RuntimeError("db integrity boom")
        self.created.append(
            {
                "ref": ref,
                "session_id": session_id,
                "run_id": run_id,
                "run_order": run_order,
            }
        )
        return ref


class RecordingHealthRepo:
    """In-memory repository-like health sink."""

    def __init__(self, *, fail: bool = False) -> None:
        self.created: list[Any] = []
        self._fail = fail

    async def create(self, record: Any) -> Any:
        if self._fail:
            raise RuntimeError("db health boom")
        self.created.append(record)
        return record
