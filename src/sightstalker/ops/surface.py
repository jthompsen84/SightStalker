"""
sightstalker.ops.surface — per-run surface handed to trusted internal plans.

``RunSurface`` exposes page creation, the accepted one-navigation guard
(``navigate``), and diagnostic-target derivation. The guard is enforced only for
plans that call ``RunSurface.navigate``; this PR does not introduce a guarded
``PageHandle`` proxy, so trusted internal plans may still use the raw
``PageHandle`` from ``new_page``. A duplicate ``navigate`` raises
``SecurityRefusal``, which maps to the public ``SecurityError`` label.
"""

from __future__ import annotations

from dataclasses import dataclass

from sightstalker.diagnostics import DiagnosticArtifactRecorder, DiagnosticTarget
from sightstalker.engines.base import BrowserContextHandle, PageHandle
from sightstalker.resilience.errors import SecurityRefusal
from sightstalker.sessions import ManagedSessionContext


@dataclass
class RunSurface:
    """Per-run surface handed to a trusted internal capture plan.

    ``RunSurface.navigate`` preserves the accepted one-navigation guard for
    plans that use this surface method. This PR does not introduce a guarded
    PageHandle proxy; trusted internal plans can still access the raw PageHandle
    returned by ``new_page``.
    """

    managed: ManagedSessionContext
    raw_navigation_url: str
    recorder: DiagnosticArtifactRecorder
    base_target: DiagnosticTarget
    _goto_count: int = 0

    @property
    def context(self) -> BrowserContextHandle:
        return self.managed.context

    async def new_page(self) -> PageHandle:
        return await self.context.new_page()

    async def navigate(self, page: PageHandle) -> None:
        if self._goto_count != 0:
            raise SecurityRefusal("exactly one navigation is permitted per run")
        self._goto_count += 1
        await page.goto(self.raw_navigation_url)

    def target_with_order(self, run_order: int) -> DiagnosticTarget:
        return self.base_target.model_copy(update={"run_order": run_order})


__all__ = ["RunSurface"]
