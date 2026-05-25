"""
sightstalker.cli.runtime — lazy browser engine resolution for the CLI.

The only active browser surface in CLI-RUNNER-1 is a single explicit
``page.goto`` driven by ``run open`` / ``diag *``. The concrete engine is
resolved here, lazily, so importing the CLI never imports a browser package or
adapter. Only ``camoufox`` is supported in this PR; other engine names fail
with a clean, sanitized error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sightstalker.cli.errors import CliBrowserError

if TYPE_CHECKING:
    from sightstalker.engines import BrowserEngine

_CAMOUFOX_UNAVAILABLE = (
    "Camoufox runtime is unavailable. Install the camoufox extra and fetch the "
    "browser binary before running browser commands."
)


def create_engine_for_name(engine_name: str) -> "BrowserEngine":
    """Return a concrete browser engine for ``engine_name`` (lazy import).

    Only ``camoufox`` is supported. The concrete adapter is imported inside
    this function body so module import never loads a browser package.
    """
    if engine_name != "camoufox":
        raise CliBrowserError(
            f"engine '{engine_name}' is not supported by this CLI release"
        )
    try:
        # Lazy: resolves the adapter symbol via the engines package (PEP 562).
        from sightstalker.engines import CamoufoxEngine
    except Exception:  # pragma: no cover - import guarded for clean error
        raise CliBrowserError(_CAMOUFOX_UNAVAILABLE) from None
    return CamoufoxEngine()


__all__ = ["create_engine_for_name"]
