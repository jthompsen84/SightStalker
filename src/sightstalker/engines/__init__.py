"""
sightstalker.engines — browser engine protocol definitions and adapters.

Import from this package rather than from submodules directly:

    from sightstalker.engines import BrowserEngine, CamoufoxEngine
"""

from __future__ import annotations

from sightstalker.engines.base import (
    BrowserContextHandle,
    BrowserEngine,
    BrowserRuntime,
    PageHandle,
)
from sightstalker.engines.camoufox import CamoufoxEngine

__all__ = [
    "BrowserContextHandle",
    "BrowserEngine",
    "BrowserRuntime",
    "CamoufoxEngine",
    "PageHandle",
]
