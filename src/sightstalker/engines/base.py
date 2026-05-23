"""
sightstalker.engines.base — browser engine protocol definitions.

These protocols define the stable seam between higher-level session/run
orchestration and concrete browser engine implementations.

Dependency rule:
    Higher-level code (sessions, runs, diagnostics, CLI) must depend on
    these protocols only. Concrete engine packages (camoufox, playwright,
    etc.) must be imported exclusively inside their engine adapter modules.

Escape hatches:
    native_page, native_context, and native_browser expose the underlying
    engine objects for low-level adapters and diagnostics. Avoid using these
    in high-level orchestration logic.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from sightstalker.models.browser import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
)
from sightstalker.models.identifiers import ContextId


@runtime_checkable
class PageHandle(Protocol):
    """
    Minimal page handle contract.

    Implementations wrap engine-native page objects internally.
    Higher layers depend only on this protocol.
    """

    @property
    def native_page(self) -> Any:
        """
        Engine-native page object.
        Intended for low-level adapters and diagnostics only.
        Avoid direct dependency on this in high-level orchestration.
        """
        ...

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout_ms: int | None = None,
    ) -> None:
        """Navigate to a URL."""
        ...

    async def title(self) -> str:
        """Return the current page title."""
        ...

    async def url(self) -> str:
        """Return the current page URL."""
        ...

    async def screenshot(
        self,
        *,
        path: str,
        full_page: bool = False,
        timeout_ms: int | None = None,
    ) -> None:
        """Capture a screenshot to the given path."""
        ...

    async def close(self) -> None:
        """Close this page."""
        ...


@runtime_checkable
class BrowserContextHandle(Protocol):
    """
    Runtime browser isolation context.

    A context belongs to one run. It may read an initial storage state on
    creation and emit a final storage state on close. It must be explicitly
    closed by the run lifecycle manager.
    """

    @property
    def context_id(self) -> ContextId:
        """Stable identifier for this context."""
        ...

    @property
    def native_context(self) -> Any:
        """
        Engine-native context object.
        Allowed for diagnostics and engine adapters.
        Avoid using this in high-level session/run logic.
        """
        ...

    async def new_page(self) -> PageHandle:
        """Create a new page within this context."""
        ...

    async def storage_state(self) -> BrowserState:
        """
        Export the current browser storage state as an immutable snapshot.
        """
        ...

    async def start_tracing(self, *, name: str | None = None) -> None:
        """Begin capturing a Playwright trace for this context."""
        ...

    async def stop_tracing(self, *, path: str) -> None:
        """Stop tracing and write the archive to the given path."""
        ...

    async def close(self) -> None:
        """Close this context and release associated resources."""
        ...


@runtime_checkable
class BrowserRuntime(Protocol):
    """
    Launched browser runtime.

    The runtime owns the engine process or remote connection and creates
    isolated browser contexts. One runtime may serve multiple contexts if
    the engine supports isolation.
    """

    @property
    def engine_name(self) -> str:
        """The name of the underlying engine (e.g. "camoufox", "mock")."""
        ...

    @property
    def native_browser(self) -> Any:
        """
        Engine-native browser or runtime object.
        Exposed at the seam for adapters; not the primary application contract.
        """
        ...

    async def new_context(
        self,
        config: BrowserContextConfig,
        *,
        initial_state: BrowserState | None = None,
        context_id: ContextId | None = None,
    ) -> BrowserContextHandle:
        """
        Create an isolated browser context.

        If initial_state is provided, the engine should apply it before
        returning the context handle.
        If context_id is provided, the context handle must use that ID.
        """
        ...

    async def close(self) -> None:
        """Close the runtime and all associated contexts."""
        ...


@runtime_checkable
class BrowserEngine(Protocol):
    """
    Browser engine abstraction.

    Implementations:
        CamoufoxEngine      — first real engine (CAMOUFOX-ENGINE-1)
        MockBrowserEngine   — test double (lives in tests/, not production)

    Future implementations:
        PlaywrightChromiumEngine
        PlaywrightFirefoxEngine

    All higher-level code must depend on this protocol, not on concrete
    browser packages.
    """

    @property
    def name(self) -> str:
        """Stable engine name matching BrowserEngineName."""
        ...

    async def launch(self, config: BrowserLaunchConfig) -> BrowserRuntime:
        """
        Launch the browser and return a runtime handle.

        The caller is responsible for calling runtime.close() when done.
        """
        ...

    async def close(self) -> None:
        """Release all resources held by this engine instance."""
        ...
