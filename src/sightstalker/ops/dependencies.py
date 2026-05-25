"""
sightstalker.ops.dependencies — application-layer dependency types.

Centralizes the dependency-injection types the ops orchestration boundary needs
from its callers. The engine protocol is imported from ``engines.base`` (never
the package surface or a concrete adapter), so importing ops never loads the
Camoufox adapter or Playwright.
"""

from __future__ import annotations

from collections.abc import Callable

from sightstalker.engines.base import BrowserEngine
from sightstalker.models import BrowserEngineName

# A factory that builds a launched-capable engine from an engine name. The CLI
# supplies this (lazily resolving Camoufox); ops never constructs engines.
EngineFactory = Callable[[BrowserEngineName], BrowserEngine]

__all__ = ["EngineFactory"]
