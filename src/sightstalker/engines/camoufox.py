"""
sightstalker.engines.camoufox — first concrete browser engine adapter.

Implements the accepted protocol chain:

    BrowserEngine -> BrowserRuntime -> BrowserContextHandle -> PageHandle

against Camoufox's async API (a Playwright-compatible Firefox build).

Architecture rules enforced here:
- This is the ONLY production module permitted to import Camoufox.
- The Camoufox import is lazy (inside the factory loader), so importing this
  module — and therefore `from sightstalker.engines import CamoufoxEngine` —
  works without Camoufox installed and without a fetched browser binary.
- Higher-level code depends only on the SightStalker protocols, never on
  Camoufox or Playwright native objects.

Scope (CAMOUFOX-ENGINE-1):
- launch, new_context, new_page, goto, title, url, screenshot,
  in-memory storage-state conversion, direct-path tracing, clean close.

Explicitly out of scope (deferred):
- persistent contexts / user_data_dir (SESSION-STATE-1)
- fingerprint mapping (fingerprint registry PRs)
- humanize, geoip, video, console capture, stealth/bypass options
- artifact management, persistence, CLI, diagnostics orchestration
"""

from __future__ import annotations

import secrets
from contextlib import AsyncExitStack
from typing import Any, Protocol, cast, runtime_checkable

from sightstalker.engines.base import (
    BrowserContextHandle,
    BrowserRuntime,
    PageHandle,
)
from sightstalker.models.browser import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
)
from sightstalker.models.identifiers import ContextId

# ---------------------------------------------------------------------------
# Private typed protocols for native (Camoufox / Playwright-compatible) objects
#
# These keep the adapter strictly typed without spreading `Any` everywhere.
# They describe only the subset of the native surface this PR uses. They are
# structural (duck-typed) and are NOT imported from camoufox or playwright.
# ---------------------------------------------------------------------------


@runtime_checkable
class _NativeTracingLike(Protocol):
    async def start(self, *, name: str | None = ...) -> Any: ...
    async def stop(self, *, path: str = ...) -> Any: ...


@runtime_checkable
class _NativePageLike(Protocol):
    @property
    def url(self) -> str: ...
    async def goto(self, url: str, **kwargs: Any) -> Any: ...
    async def title(self) -> str: ...
    async def screenshot(self, **kwargs: Any) -> Any: ...
    async def close(self) -> Any: ...


@runtime_checkable
class _NativeContextLike(Protocol):
    @property
    def tracing(self) -> _NativeTracingLike: ...
    async def new_page(self) -> _NativePageLike: ...
    async def storage_state(self, **kwargs: Any) -> dict[str, Any]: ...
    def set_default_timeout(self, timeout: int) -> Any: ...
    def set_default_navigation_timeout(self, timeout: int) -> Any: ...
    async def close(self) -> Any: ...


@runtime_checkable
class _NativeBrowserLike(Protocol):
    async def new_context(self, **kwargs: Any) -> _NativeContextLike: ...
    async def close(self) -> Any: ...


class _AsyncCamoufoxManagerLike(Protocol):
    """The object returned by AsyncCamoufox(**kwargs); an async context manager."""

    async def __aenter__(self) -> _NativeBrowserLike: ...
    async def __aexit__(self, *exc_info: Any) -> Any: ...


class _AsyncCamoufoxFactoryLike(Protocol):
    """Callable matching AsyncCamoufox's constructor signature."""

    def __call__(self, **kwargs: Any) -> _AsyncCamoufoxManagerLike: ...


# ---------------------------------------------------------------------------
# Lazy loader
# ---------------------------------------------------------------------------


def _load_async_camoufox() -> _AsyncCamoufoxFactoryLike:
    """
    Import and return the AsyncCamoufox factory lazily.

    Importing camoufox is deferred to call time so that this module imports
    cleanly without the camoufox package or a fetched browser binary.
    """
    from camoufox.async_api import AsyncCamoufox  # type: ignore  # noqa: PLC0415

    return cast("_AsyncCamoufoxFactoryLike", AsyncCamoufox)


# ---------------------------------------------------------------------------
# Config mapping helpers
# ---------------------------------------------------------------------------


def _build_launch_kwargs(config: BrowserLaunchConfig) -> dict[str, Any]:
    """
    Map a BrowserLaunchConfig into Camoufox launch kwargs.

    Rejects deferred features (user_data_dir, fingerprint) explicitly.
    Never logs the resulting kwargs (they may contain proxy credentials).
    """
    if config.user_data_dir is not None:
        raise ValueError(
            "Camoufox persistent user_data_dir launch is deferred to SESSION-STATE-1"
        )
    if config.fingerprint is not None:
        raise ValueError(
            "FingerprintConfig mapping is deferred to profile/fingerprint registry PRs"
        )

    kwargs: dict[str, Any] = {
        "headless": config.mode == "headless",
        "slow_mo": config.slow_mo_ms,
        "timeout": config.timeout_ms,
    }

    if config.executable_path is not None:
        kwargs["executable_path"] = str(config.executable_path)

    if config.args:
        kwargs["args"] = list(config.args)

    if config.env:
        kwargs["env"] = dict(config.env)

    if config.proxy is not None:
        proxy_kwargs: dict[str, Any] = {"server": config.proxy.server}
        if config.proxy.username is not None:
            proxy_kwargs["username"] = config.proxy.username
        if config.proxy.password is not None:
            proxy_kwargs["password"] = config.proxy.password.get_secret_value()
        if config.proxy.bypass is not None:
            proxy_kwargs["bypass"] = config.proxy.bypass
        kwargs["proxy"] = proxy_kwargs

    return kwargs


def _build_context_kwargs(config: BrowserContextConfig) -> dict[str, Any]:
    """
    Map a BrowserContextConfig into Playwright-compatible context kwargs.

    Timeouts are applied after creation via set_default_* and are not
    included here. Never logs the resulting kwargs (headers may be sensitive).
    """
    kwargs: dict[str, Any] = {
        "accept_downloads": config.accept_downloads,
        "java_script_enabled": config.java_script_enabled,
        "ignore_https_errors": config.ignore_https_errors,
    }

    if config.viewport is not None:
        kwargs["viewport"] = {
            "width": config.viewport.width,
            "height": config.viewport.height,
        }

    if config.locale is not None:
        kwargs["locale"] = config.locale

    if config.timezone_id is not None:
        kwargs["timezone_id"] = config.timezone_id

    if config.extra_http_headers:
        kwargs["extra_http_headers"] = dict(config.extra_http_headers)

    if config.permissions:
        kwargs["permissions"] = list(config.permissions)

    if config.record_har_path is not None:
        kwargs["record_har_path"] = str(config.record_har_path)

    if config.record_video_dir is not None:
        kwargs["record_video_dir"] = str(config.record_video_dir)

    return kwargs


def _state_to_native(state: BrowserState) -> dict[str, Any]:
    """Convert a SightStalker BrowserState into a Playwright storage_state dict."""
    return {
        "cookies": list(state.cookies),
        "origins": list(state.origins),
    }


def _native_to_state(
    raw: dict[str, Any],
    *,
    indexed_db_included: bool,
) -> BrowserState:
    """Convert a native storage_state dict into an immutable BrowserState."""
    cookies = raw.get("cookies", ())
    origins = raw.get("origins", ())
    return BrowserState(
        cookies=tuple(cookies),
        origins=tuple(origins),
        indexed_db_included=indexed_db_included,
        engine_name="camoufox",
    )


def _generate_context_id() -> ContextId:
    """
    Generate an auto context id satisfying the ContextId pattern:
        ^ctx_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$

    Produces "ctx_auto_<12 hex chars>" (21 chars total). No global ID service.
    """
    return f"ctx_auto_{secrets.token_hex(6)}"


# ---------------------------------------------------------------------------
# Page handle
# ---------------------------------------------------------------------------


class CamoufoxPageHandle:
    """PageHandle implementation wrapping a native Playwright-compatible page."""

    def __init__(self, native_page: _NativePageLike) -> None:
        self._page = native_page
        self._closed = False

    @property
    def native_page(self) -> Any:
        return self._page

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout_ms: int | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"wait_until": wait_until}
        if timeout_ms is not None:
            kwargs["timeout"] = timeout_ms
        await self._page.goto(url, **kwargs)

    async def title(self) -> str:
        return await self._page.title()

    async def url(self) -> str:
        return str(self._page.url)

    async def screenshot(
        self,
        *,
        path: str,
        full_page: bool = False,
        timeout_ms: int | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"path": path, "full_page": full_page}
        if timeout_ms is not None:
            kwargs["timeout"] = timeout_ms
        await self._page.screenshot(**kwargs)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._page.close()


# ---------------------------------------------------------------------------
# Context handle
# ---------------------------------------------------------------------------


class CamoufoxContextHandle:
    """BrowserContextHandle implementation wrapping a native browser context."""

    def __init__(
        self,
        *,
        context_id: ContextId,
        native_context: _NativeContextLike,
    ) -> None:
        self._context_id = context_id
        self._context = native_context
        self._closed = False

    @property
    def context_id(self) -> ContextId:
        return self._context_id

    @property
    def native_context(self) -> Any:
        return self._context

    async def new_page(self) -> PageHandle:
        page = await self._context.new_page()
        return CamoufoxPageHandle(page)

    async def storage_state(self) -> BrowserState:
        # Prefer IndexedDB inclusion when the installed API supports the kwarg.
        try:
            raw = await self._context.storage_state(indexed_db=True)
            indexed_db_included = True
        except TypeError:
            raw = await self._context.storage_state()
            indexed_db_included = False
        return _native_to_state(raw, indexed_db_included=indexed_db_included)

    async def start_tracing(self, *, name: str | None = None) -> None:
        await self._context.tracing.start(name=name)

    async def stop_tracing(self, *, path: str) -> None:
        await self._context.tracing.stop(path=path)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._context.close()


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class CamoufoxRuntime:
    """BrowserRuntime implementation owning the launched browser + exit stack."""

    def __init__(
        self,
        *,
        native_browser: _NativeBrowserLike,
        exit_stack: AsyncExitStack,
        engine_name: str = "camoufox",
    ) -> None:
        self._browser = native_browser
        self._exit_stack = exit_stack
        self._engine_name = engine_name
        self._closed = False

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def native_browser(self) -> Any:
        return self._browser

    async def new_context(
        self,
        config: BrowserContextConfig,
        *,
        initial_state: BrowserState | None = None,
        context_id: ContextId | None = None,
    ) -> BrowserContextHandle:
        context_kwargs = _build_context_kwargs(config)
        if initial_state is not None:
            context_kwargs["storage_state"] = _state_to_native(initial_state)

        native_context = await self._browser.new_context(**context_kwargs)

        # Apply default timeouts after creation (sync methods in Playwright).
        native_context.set_default_timeout(config.default_timeout_ms)
        native_context.set_default_navigation_timeout(config.navigation_timeout_ms)

        resolved_id = context_id if context_id is not None else _generate_context_id()
        return CamoufoxContextHandle(
            context_id=resolved_id,
            native_context=native_context,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Closing the exit stack closes the AsyncCamoufox context manager,
        # which in turn closes the underlying browser.
        await self._exit_stack.aclose()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CamoufoxEngine:
    """
    BrowserEngine implementation backed by Camoufox.

    The optional async_camoufox_factory injection point lets unit tests
    supply a fake factory without installing or launching Camoufox.
    """

    def __init__(
        self,
        async_camoufox_factory: _AsyncCamoufoxFactoryLike | None = None,
    ) -> None:
        self._async_camoufox_factory = async_camoufox_factory

    @property
    def name(self) -> str:
        return "camoufox"

    async def launch(self, config: BrowserLaunchConfig) -> BrowserRuntime:
        launch_kwargs = _build_launch_kwargs(config)
        factory = self._async_camoufox_factory or _load_async_camoufox()

        stack = AsyncExitStack()
        try:
            manager = factory(**launch_kwargs)
            native_browser = await stack.enter_async_context(cast("Any", manager))
        except BaseException:
            # Ensure a partially opened stack is fully unwound on failure.
            await stack.aclose()
            raise

        return CamoufoxRuntime(
            native_browser=cast("_NativeBrowserLike", native_browser),
            exit_stack=stack,
        )

    async def close(self) -> None:
        # The engine holds no long-lived resources; runtimes own their stacks.
        return None

