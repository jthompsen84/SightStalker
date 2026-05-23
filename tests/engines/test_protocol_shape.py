"""
Engine protocol shape tests for FOUNDATION-CONTRACT-1.

Verifies:
- Mock implementations satisfy all four runtime-checkable protocols.
- Protocol hierarchy is traversable (engine → runtime → context → page).
- No concrete browser package is imported.

Mock classes are defined locally in this file. They must not exist in
production code.
"""

from __future__ import annotations

from typing import Any

import pytest

from sightstalker.engines import (
    BrowserContextHandle,
    BrowserEngine,
    BrowserRuntime,
    PageHandle,
)
from sightstalker.models import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
)
from sightstalker.models.identifiers import ContextId

# ---------------------------------------------------------------------------
# Test fixture IDs
# ---------------------------------------------------------------------------

CTX_ID: ContextId = "ctx_test_default"

# ---------------------------------------------------------------------------
# Mock implementations (test-only, must not exist in production code)
# ---------------------------------------------------------------------------


class MockPageHandle:
    """Test double for PageHandle protocol."""

    @property
    def native_page(self) -> Any:
        return object()

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout_ms: int | None = None,
    ) -> None:
        pass

    async def title(self) -> str:
        return "Mock Page Title"

    async def url(self) -> str:
        return "https://example.com"

    async def screenshot(
        self,
        *,
        path: str,
        full_page: bool = False,
        timeout_ms: int | None = None,
    ) -> None:
        pass

    async def close(self) -> None:
        pass


class MockBrowserContextHandle:
    """Test double for BrowserContextHandle protocol."""

    @property
    def context_id(self) -> ContextId:
        return CTX_ID

    @property
    def native_context(self) -> Any:
        return object()

    async def new_page(self) -> PageHandle:
        return MockPageHandle()

    async def storage_state(self) -> BrowserState:
        return BrowserState(engine_name="mock")

    async def start_tracing(self, *, name: str | None = None) -> None:
        pass

    async def stop_tracing(self, *, path: str) -> None:
        pass

    async def close(self) -> None:
        pass


class MockBrowserRuntime:
    """Test double for BrowserRuntime protocol."""

    @property
    def engine_name(self) -> str:
        return "mock"

    @property
    def native_browser(self) -> Any:
        return object()

    async def new_context(
        self,
        config: BrowserContextConfig,
        *,
        initial_state: BrowserState | None = None,
        context_id: ContextId | None = None,
    ) -> BrowserContextHandle:
        return MockBrowserContextHandle()

    async def close(self) -> None:
        pass


class MockBrowserEngine:
    """Test double for BrowserEngine protocol."""

    @property
    def name(self) -> str:
        return "mock"

    async def launch(self, config: BrowserLaunchConfig) -> BrowserRuntime:
        return MockBrowserRuntime()

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# 1–4. Protocol isinstance checks (runtime_checkable)
# ---------------------------------------------------------------------------


def test_mock_engine_satisfies_browser_engine_protocol() -> None:
    engine = MockBrowserEngine()
    assert isinstance(engine, BrowserEngine)


def test_mock_runtime_satisfies_browser_runtime_protocol() -> None:
    runtime = MockBrowserRuntime()
    assert isinstance(runtime, BrowserRuntime)


def test_mock_context_satisfies_browser_context_handle_protocol() -> None:
    context = MockBrowserContextHandle()
    assert isinstance(context, BrowserContextHandle)


def test_mock_page_satisfies_page_handle_protocol() -> None:
    page = MockPageHandle()
    assert isinstance(page, PageHandle)


# ---------------------------------------------------------------------------
# 5. Mock engine returns mock runtime from launch()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_engine_launch_returns_browser_runtime() -> None:
    engine = MockBrowserEngine()
    config = BrowserLaunchConfig()
    runtime = await engine.launch(config)
    assert isinstance(runtime, BrowserRuntime)
    assert runtime.engine_name == "mock"


# ---------------------------------------------------------------------------
# 6. Mock runtime returns mock context from new_context()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_runtime_new_context_returns_context_handle() -> None:
    runtime = MockBrowserRuntime()
    config = BrowserContextConfig()
    context = await runtime.new_context(config)
    assert isinstance(context, BrowserContextHandle)
    assert context.context_id == CTX_ID


# ---------------------------------------------------------------------------
# 7. Mock context returns mock page from new_page()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_context_new_page_returns_page_handle() -> None:
    context = MockBrowserContextHandle()
    page = await context.new_page()
    assert isinstance(page, PageHandle)


# ---------------------------------------------------------------------------
# 8. Mock context returns valid BrowserState from storage_state()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_context_storage_state_returns_browser_state() -> None:
    context = MockBrowserContextHandle()
    state = await context.storage_state()
    assert isinstance(state, BrowserState)
    assert state.engine_name == "mock"
    assert isinstance(state.cookies, tuple)
    assert isinstance(state.origins, tuple)


# ---------------------------------------------------------------------------
# 9. Full mock traversal: engine → runtime → context → page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_full_protocol_traversal() -> None:
    engine = MockBrowserEngine()
    runtime = await engine.launch(BrowserLaunchConfig())
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    state = await context.storage_state()

    assert isinstance(engine, BrowserEngine)
    assert isinstance(runtime, BrowserRuntime)
    assert isinstance(context, BrowserContextHandle)
    assert isinstance(page, PageHandle)
    assert isinstance(state, BrowserState)

    await page.close()
    await context.close()
    await runtime.close()
    await engine.close()


# ---------------------------------------------------------------------------
# 10. No concrete browser package imported
# ---------------------------------------------------------------------------


def test_no_concrete_browser_package_imported() -> None:
    import sys

    banned = {
        "camoufox",
        "playwright",
        "playwright.async_api",
        "playwright.sync_api",
    }
    imported = set(sys.modules.keys())
    violations = banned & imported
    assert not violations, (
        f"Banned browser packages were imported during protocol tests: {violations}"
    )
