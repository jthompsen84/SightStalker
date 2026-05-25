"""
sightstalker.resilience.timeouts — model-level timeout policy.

``TimeoutPolicy`` is a declarative model only. RESILIENCE-1 exposes accepted
default budgets but does NOT wrap operations in ``asyncio.wait_for``, change
browser adapter timeout semantics, add automatic timeout retries, or tighten
the accepted CLI ``--timeout-ms`` validation. Defaults mirror the accepted
browser/context/navigation/diagnostics configuration.
"""

from __future__ import annotations

from pydantic import Field

from sightstalker.models import ToolkitModel

_MIN_MS = 100
_MAX_MS = 3_600_000


class TimeoutPolicy(ToolkitModel):
    """Declarative per-concern timeout budgets, in milliseconds.

    Each field is bounded to ``[100, 3_600_000]`` ms. Defaults match the
    accepted configuration: navigation 45_000; launch/context/diagnostics/
    database/artifact-io 30_000.
    """

    browser_launch_ms: int = Field(default=30_000, ge=_MIN_MS, le=_MAX_MS)
    browser_context_ms: int = Field(default=30_000, ge=_MIN_MS, le=_MAX_MS)
    navigation_ms: int = Field(default=45_000, ge=_MIN_MS, le=_MAX_MS)
    diagnostics_ms: int = Field(default=30_000, ge=_MIN_MS, le=_MAX_MS)
    database_ms: int = Field(default=30_000, ge=_MIN_MS, le=_MAX_MS)
    artifact_io_ms: int = Field(default=30_000, ge=_MIN_MS, le=_MAX_MS)


__all__ = ["TimeoutPolicy"]
