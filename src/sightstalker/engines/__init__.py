"""
sightstalker.engines — browser engine protocol definitions and adapters.

Import from this package rather than from submodules directly:

    from sightstalker.engines import BrowserEngine, CamoufoxEngine

The concrete ``CamoufoxEngine`` adapter is imported lazily (PEP 562) so that
importing protocol-only consumers — for example ``sightstalker.engines.base``
or ``sightstalker.diagnostics`` — does not pull the adapter module into
``sys.modules``. Accessing ``CamoufoxEngine`` from this package still works
exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sightstalker.engines.base import (
    BrowserContextHandle,
    BrowserEngine,
    BrowserRuntime,
    PageHandle,
)

if TYPE_CHECKING:
    from sightstalker.engines.camoufox import CamoufoxEngine

__all__ = [
    "BrowserContextHandle",
    "BrowserEngine",
    "BrowserRuntime",
    "CamoufoxEngine",
    "PageHandle",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve the concrete adapter on first access (PEP 562)."""
    if name == "CamoufoxEngine":
        from sightstalker.engines.camoufox import CamoufoxEngine

        return CamoufoxEngine

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
