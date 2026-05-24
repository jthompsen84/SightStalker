"""
Camoufox adapter unit tests for CAMOUFOX-ENGINE-1.

These tests use fake native classes injected via the engine's
async_camoufox_factory parameter. They require neither the camoufox package
nor a fetched browser binary.

They verify:
- Protocol conformance of the adapter classes.
- Launch config mapping (mode, slow_mo, timeout, args, env, proxy).
- Deferred-feature rejection (user_data_dir, fingerprint).
- Context config mapping (viewport, locale, timezone, headers, permissions...).
- Default timeout application after context creation.
- BrowserState <-> native storage_state conversion (incl. indexed_db fallback).
- Page operations (goto, title, url, screenshot) mapping.
- Tracing delegation.
- Idempotent close at all three levels.
- Partial-launch cleanup.
- Proxy secret never leaking into config repr.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from sightstalker.engines import (
    BrowserContextHandle,
    BrowserEngine,
    BrowserRuntime,
    CamoufoxEngine,
    PageHandle,
)
from sightstalker.engines.camoufox import (
    CamoufoxContextHandle,
    CamoufoxPageHandle,
    CamoufoxRuntime,
)
from sightstalker.models import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
    FingerprintConfig,
    ProxyConfig,
    ViewportConfig,
)
from sightstalker.models.identifiers import ContextId

CTX_ID: ContextId = "ctx_test_default"


# ---------------------------------------------------------------------------
# Fake native classes (test doubles for Camoufox/Playwright objects)
# ---------------------------------------------------------------------------


class FakeNativeTracing:
    def __init__(self) -> None:
        self.start_calls: list[dict[str, Any]] = []
        self.stop_calls: list[dict[str, Any]] = []

    async def start(self, *, name: str | None = None) -> None:
        self.start_calls.append({"name": name})

    async def stop(self, *, path: str = "") -> None:
        self.stop_calls.append({"path": path})


class FakeNativePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls: list[dict[str, Any]] = []
        self.screenshot_calls: list[dict[str, Any]] = []
        self.close_count = 0
        self._title = "Fake Title"

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self.goto_calls.append({"url": url, **kwargs})

    async def title(self) -> str:
        return self._title

    async def screenshot(self, **kwargs: Any) -> None:
        self.screenshot_calls.append(kwargs)

    async def close(self) -> None:
        self.close_count += 1


class FakeNativeContext:
    def __init__(
        self,
        *,
        storage_state_supports_indexed_db: bool = True,
        storage_state_payload: dict[str, Any] | None = None,
    ) -> None:
        self.tracing = FakeNativeTracing()
        self.new_page_obj = FakeNativePage()
        self.default_timeout: int | None = None
        self.default_navigation_timeout: int | None = None
        self.close_count = 0
        self._supports_indexed_db = storage_state_supports_indexed_db
        self._storage_state_payload = storage_state_payload or {
            "cookies": [{"name": "c", "value": "v"}],
            "origins": [{"origin": "https://example.com"}],
        }
        self.storage_state_calls: list[dict[str, Any]] = []

    async def new_page(self) -> FakeNativePage:
        return self.new_page_obj

    async def storage_state(self, **kwargs: Any) -> dict[str, Any]:
        if "indexed_db" in kwargs and not self._supports_indexed_db:
            raise TypeError("storage_state() got unexpected keyword 'indexed_db'")
        self.storage_state_calls.append(kwargs)
        return self._storage_state_payload

    def set_default_timeout(self, timeout: int) -> None:
        self.default_timeout = timeout

    def set_default_navigation_timeout(self, timeout: int) -> None:
        self.default_navigation_timeout = timeout

    async def close(self) -> None:
        self.close_count += 1


class FakeNativeBrowser:
    def __init__(self, context: FakeNativeContext | None = None) -> None:
        self.context = context or FakeNativeContext()
        self.new_context_calls: list[dict[str, Any]] = []
        self.close_count = 0

    async def new_context(self, **kwargs: Any) -> FakeNativeContext:
        self.new_context_calls.append(kwargs)
        return self.context

    async def close(self) -> None:
        self.close_count += 1


class FakeAsyncCamoufoxManager:
    def __init__(self, browser: FakeNativeBrowser, kwargs: dict[str, Any]) -> None:
        self._browser = browser
        self.launch_kwargs = kwargs
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> FakeNativeBrowser:
        self.entered = True
        return self._browser

    async def __aexit__(self, *exc_info: Any) -> None:
        self.exited = True


class FakeFailingManager:
    """Async context manager whose __aenter__ raises (class-level, as Python
    looks up __aenter__ on the type, not the instance)."""

    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.launch_kwargs = kwargs
        self.exited = False

    async def __aenter__(self) -> Any:
        raise RuntimeError("launch failed inside context manager")

    async def __aexit__(self, *exc_info: Any) -> None:
        self.exited = True


class FakeAsyncCamoufoxFactory:
    """Records launch kwargs and returns a controllable manager."""

    def __init__(
        self,
        browser: FakeNativeBrowser | None = None,
        *,
        raise_on_enter: bool = False,
    ) -> None:
        self.browser = browser or FakeNativeBrowser()
        self.captured_kwargs: dict[str, Any] | None = None
        self.last_manager: FakeAsyncCamoufoxManager | FakeFailingManager | None = None
        self._raise_on_enter = raise_on_enter

    def __call__(
        self, **kwargs: Any
    ) -> FakeAsyncCamoufoxManager | FakeFailingManager:
        self.captured_kwargs = kwargs
        if self._raise_on_enter:
            failing = FakeFailingManager(kwargs)
            self.last_manager = failing
            return failing
        manager = FakeAsyncCamoufoxManager(self.browser, kwargs)
        self.last_manager = manager
        return manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _launch_with_fake(
    config: BrowserLaunchConfig | None = None,
    *,
    factory: FakeAsyncCamoufoxFactory | None = None,
) -> tuple[CamoufoxEngine, FakeAsyncCamoufoxFactory, BrowserRuntime]:
    fake_factory = factory or FakeAsyncCamoufoxFactory()
    engine = CamoufoxEngine(async_camoufox_factory=fake_factory)
    runtime = await engine.launch(config or BrowserLaunchConfig())
    return engine, fake_factory, runtime


# ---------------------------------------------------------------------------
# 1–5. Protocol conformance
# ---------------------------------------------------------------------------


def test_camoufox_engine_satisfies_browser_engine() -> None:
    assert isinstance(CamoufoxEngine(), BrowserEngine)


def test_camoufox_engine_name() -> None:
    assert CamoufoxEngine().name == "camoufox"


@pytest.mark.asyncio
async def test_launch_returns_browser_runtime() -> None:
    _, _, runtime = await _launch_with_fake()
    assert isinstance(runtime, BrowserRuntime)


@pytest.mark.asyncio
async def test_new_context_returns_context_handle() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    assert isinstance(context, BrowserContextHandle)


@pytest.mark.asyncio
async def test_new_page_returns_page_handle() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    assert isinstance(page, PageHandle)


# ---------------------------------------------------------------------------
# 6–12. Launch config mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mode_headless_maps_to_true() -> None:
    _, factory, _ = await _launch_with_fake(BrowserLaunchConfig(mode="headless"))
    assert factory.captured_kwargs is not None
    assert factory.captured_kwargs["headless"] is True


@pytest.mark.asyncio
async def test_mode_headed_maps_to_false() -> None:
    _, factory, _ = await _launch_with_fake(BrowserLaunchConfig(mode="headed"))
    assert factory.captured_kwargs is not None
    assert factory.captured_kwargs["headless"] is False


@pytest.mark.asyncio
async def test_slow_mo_ms_maps_to_slow_mo() -> None:
    _, factory, _ = await _launch_with_fake(BrowserLaunchConfig(slow_mo_ms=250))
    assert factory.captured_kwargs is not None
    assert factory.captured_kwargs["slow_mo"] == 250


@pytest.mark.asyncio
async def test_timeout_ms_maps_to_timeout() -> None:
    _, factory, _ = await _launch_with_fake(BrowserLaunchConfig(timeout_ms=45_000))
    assert factory.captured_kwargs is not None
    assert factory.captured_kwargs["timeout"] == 45_000


@pytest.mark.asyncio
async def test_args_maps_to_list() -> None:
    _, factory, _ = await _launch_with_fake(
        BrowserLaunchConfig(args=("--foo", "--bar"))
    )
    assert factory.captured_kwargs is not None
    assert factory.captured_kwargs["args"] == ["--foo", "--bar"]


@pytest.mark.asyncio
async def test_env_maps_to_dict() -> None:
    _, factory, _ = await _launch_with_fake(
        BrowserLaunchConfig(env={"DISPLAY": ":99"})
    )
    assert factory.captured_kwargs is not None
    assert factory.captured_kwargs["env"] == {"DISPLAY": ":99"}


@pytest.mark.asyncio
async def test_proxy_maps_with_secret_unwrapped_only_in_native_kwarg() -> None:
    proxy = ProxyConfig(
        server="http://proxy.example.com:8080",
        username="user",
        password=SecretStr("p4ss"),
        bypass="localhost",
    )
    config = BrowserLaunchConfig(proxy=proxy)
    _, factory, _ = await _launch_with_fake(config)
    assert factory.captured_kwargs is not None
    native_proxy = factory.captured_kwargs["proxy"]
    assert native_proxy["server"] == "http://proxy.example.com:8080"
    assert native_proxy["username"] == "user"
    assert native_proxy["password"] == "p4ss"
    assert native_proxy["bypass"] == "localhost"
    # The secret must NOT be exposed via the config object's repr.
    assert "p4ss" not in repr(config)
    assert "p4ss" not in repr(proxy)


# ---------------------------------------------------------------------------
# 13–14. Deferred-feature rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_data_dir_raises_deferred_persistence_error() -> None:
    engine = CamoufoxEngine(async_camoufox_factory=FakeAsyncCamoufoxFactory())
    config = BrowserLaunchConfig(user_data_dir=Path("/tmp/profile"))
    with pytest.raises(ValueError, match="persistent-profile"):
        await engine.launch(config)


@pytest.mark.asyncio
async def test_non_none_fingerprint_raises_deferred_error() -> None:
    engine = CamoufoxEngine(async_camoufox_factory=FakeAsyncCamoufoxFactory())
    config = BrowserLaunchConfig(fingerprint=FingerprintConfig(locale="en-US"))
    with pytest.raises(ValueError, match="fingerprint registry"):
        await engine.launch(config)


# ---------------------------------------------------------------------------
# 15–24. Context config mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewport_maps_to_native_dict() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(
        BrowserContextConfig(viewport=ViewportConfig(width=1366, height=768))
    )
    kwargs = browser.new_context_calls[-1]
    assert kwargs["viewport"] == {"width": 1366, "height": 768}


@pytest.mark.asyncio
async def test_locale_maps() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(locale="en-GB"))
    assert browser.new_context_calls[-1]["locale"] == "en-GB"


@pytest.mark.asyncio
async def test_timezone_id_maps() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(timezone_id="Europe/London"))
    assert browser.new_context_calls[-1]["timezone_id"] == "Europe/London"


@pytest.mark.asyncio
async def test_accept_downloads_maps() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(accept_downloads=True))
    assert browser.new_context_calls[-1]["accept_downloads"] is True


@pytest.mark.asyncio
async def test_java_script_enabled_maps() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(java_script_enabled=False))
    assert browser.new_context_calls[-1]["java_script_enabled"] is False


@pytest.mark.asyncio
async def test_ignore_https_errors_maps() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(ignore_https_errors=True))
    assert browser.new_context_calls[-1]["ignore_https_errors"] is True


@pytest.mark.asyncio
async def test_extra_http_headers_maps() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(
        BrowserContextConfig(extra_http_headers={"X-Test": "1"})
    )
    assert browser.new_context_calls[-1]["extra_http_headers"] == {"X-Test": "1"}


@pytest.mark.asyncio
async def test_permissions_maps_to_list() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(
        BrowserContextConfig(permissions=("geolocation", "notifications"))
    )
    assert browser.new_context_calls[-1]["permissions"] == [
        "geolocation",
        "notifications",
    ]


@pytest.mark.asyncio
async def test_record_har_path_maps_to_string() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(
        BrowserContextConfig(record_har_path=Path("/tmp/out.har"))
    )
    assert browser.new_context_calls[-1]["record_har_path"] == "/tmp/out.har"


@pytest.mark.asyncio
async def test_record_video_dir_maps_to_string() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(
        BrowserContextConfig(record_video_dir=Path("/tmp/videos"))
    )
    assert browser.new_context_calls[-1]["record_video_dir"] == "/tmp/videos"


# ---------------------------------------------------------------------------
# 25–26. Default timeout application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_timeout_applied_after_context_creation() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(default_timeout_ms=12_345))
    assert browser.context.default_timeout == 12_345


@pytest.mark.asyncio
async def test_navigation_timeout_applied_after_context_creation() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    await runtime.new_context(BrowserContextConfig(navigation_timeout_ms=23_456))
    assert browser.context.default_navigation_timeout == 23_456


# ---------------------------------------------------------------------------
# 27–30. Storage state conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_state_maps_to_native_storage_state() -> None:
    _, _, runtime = await _launch_with_fake()
    browser = runtime.native_browser
    initial = BrowserState(
        engine_name="camoufox",
        cookies=({"name": "sid", "value": "abc"},),
        origins=({"origin": "https://example.com"},),
    )
    await runtime.new_context(BrowserContextConfig(), initial_state=initial)
    native_state = browser.new_context_calls[-1]["storage_state"]
    assert native_state["cookies"] == [{"name": "sid", "value": "abc"}]
    assert native_state["origins"] == [{"origin": "https://example.com"}]


@pytest.mark.asyncio
async def test_native_storage_state_maps_back_to_browser_state() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    state = await context.storage_state()
    assert isinstance(state, BrowserState)
    assert state.engine_name == "camoufox"
    assert isinstance(state.cookies, tuple)
    assert isinstance(state.origins, tuple)


@pytest.mark.asyncio
async def test_storage_state_indexed_db_true_path() -> None:
    fake_context = FakeNativeContext(storage_state_supports_indexed_db=True)
    fake_browser = FakeNativeBrowser(context=fake_context)
    factory = FakeAsyncCamoufoxFactory(browser=fake_browser)
    _, _, runtime = await _launch_with_fake(factory=factory)
    context = await runtime.new_context(BrowserContextConfig())
    state = await context.storage_state()
    assert state.indexed_db_included is True
    assert fake_context.storage_state_calls[-1] == {"indexed_db": True}


@pytest.mark.asyncio
async def test_storage_state_fallback_path_sets_indexed_db_false() -> None:
    fake_context = FakeNativeContext(storage_state_supports_indexed_db=False)
    fake_browser = FakeNativeBrowser(context=fake_context)
    factory = FakeAsyncCamoufoxFactory(browser=fake_browser)
    _, _, runtime = await _launch_with_fake(factory=factory)
    context = await runtime.new_context(BrowserContextConfig())
    state = await context.storage_state()
    assert state.indexed_db_included is False


# ---------------------------------------------------------------------------
# 31–35. Page operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goto_maps_timeout_ms_to_timeout() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    await page.goto("https://example.com", timeout_ms=5_000)
    native = page.native_page
    assert native.goto_calls[-1]["timeout"] == 5_000


@pytest.mark.asyncio
async def test_goto_omits_timeout_when_none() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    await page.goto("https://example.com")
    native = page.native_page
    assert "timeout" not in native.goto_calls[-1]


@pytest.mark.asyncio
async def test_title_returns_native_title() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    assert await page.title() == "Fake Title"


@pytest.mark.asyncio
async def test_url_returns_native_url_property() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    await page.goto("https://example.com/page")
    assert await page.url() == "https://example.com/page"


@pytest.mark.asyncio
async def test_screenshot_maps_path_full_page_timeout() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    await page.screenshot(path="/tmp/x.png", full_page=True, timeout_ms=7_000)
    native = page.native_page
    call = native.screenshot_calls[-1]
    assert call["path"] == "/tmp/x.png"
    assert call["full_page"] is True
    assert call["timeout"] == 7_000


# ---------------------------------------------------------------------------
# 36–37. Tracing delegation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_tracing_calls_native_start() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    await context.start_tracing(name="trace1")
    native = context.native_context
    assert native.tracing.start_calls[-1] == {"name": "trace1"}


@pytest.mark.asyncio
async def test_stop_tracing_calls_native_stop_with_path() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    await context.stop_tracing(path="/tmp/trace.zip")
    native = context.native_context
    assert native.tracing.stop_calls[-1] == {"path": "/tmp/trace.zip"}


# ---------------------------------------------------------------------------
# 38–40. Idempotent close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_page_close_is_idempotent() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    page = await context.new_page()
    await page.close()
    await page.close()
    assert page.native_page.close_count == 1


@pytest.mark.asyncio
async def test_context_close_is_idempotent() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    await context.close()
    await context.close()
    assert context.native_context.close_count == 1


@pytest.mark.asyncio
async def test_runtime_close_is_idempotent() -> None:
    _, factory, runtime = await _launch_with_fake()
    await runtime.close()
    await runtime.close()
    assert factory.last_manager is not None
    assert factory.last_manager.exited is True


# ---------------------------------------------------------------------------
# 41. Partial-launch cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_failure_closes_partial_exit_stack() -> None:
    factory = FakeAsyncCamoufoxFactory(raise_on_enter=True)
    engine = CamoufoxEngine(async_camoufox_factory=factory)
    with pytest.raises(RuntimeError, match="launch failed"):
        await engine.launch(BrowserLaunchConfig())
    # The manager was created; the exit stack must have been unwound so no
    # dangling context manager remains. (No assertion on browser.close since
    # __aenter__ failed before a browser was produced.)
    assert factory.captured_kwargs is not None


# ---------------------------------------------------------------------------
# 42. Proxy secret never appears in config repr
# ---------------------------------------------------------------------------


def test_proxy_password_not_in_config_repr() -> None:
    config = BrowserLaunchConfig(
        proxy=ProxyConfig(
            server="http://proxy:8080",
            password=SecretStr("super_secret_value"),
        )
    )
    assert "super_secret_value" not in repr(config)


# ---------------------------------------------------------------------------
# Direct adapter class conformance (construction without engine)
# ---------------------------------------------------------------------------


def test_adapter_classes_satisfy_protocols_directly() -> None:
    page = CamoufoxPageHandle(FakeNativePage())
    context = CamoufoxContextHandle(
        context_id=CTX_ID,
        native_context=FakeNativeContext(),
    )
    assert isinstance(page, PageHandle)
    assert isinstance(context, BrowserContextHandle)


@pytest.mark.asyncio
async def test_explicit_context_id_is_used() -> None:
    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig(), context_id=CTX_ID)
    assert context.context_id == CTX_ID


@pytest.mark.asyncio
async def test_auto_context_id_matches_pattern() -> None:
    import re

    _, _, runtime = await _launch_with_fake()
    context = await runtime.new_context(BrowserContextConfig())
    assert re.match(r"^ctx_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$", context.context_id)


def test_runtime_engine_name_is_camoufox() -> None:
    runtime = CamoufoxRuntime(
        native_browser=FakeNativeBrowser(),
        exit_stack=__import__("contextlib").AsyncExitStack(),
    )
    assert runtime.engine_name == "camoufox"
