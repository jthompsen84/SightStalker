"""
sightstalker.ops — application orchestration boundary for managed runs.

This package owns the shared managed-run orchestration that previously lived in
``sightstalker.cli.runs``. The CLI delegates managed execution here; ops remains
presentation-neutral and depends only on sessions, artifacts, diagnostics,
persistence, models, resilience, the engine *protocols* in
``sightstalker.engines.base``, and the narrow environment protocol/model
contracts used for pre-launch resolution and the initializer scope.

As of v0.4.5, ops also owns the trusted post-context/pre-page initializer seam
(``ContextInitializer`` / ``ContextInitializationScope`` /
``ContextInitializerChain``). The chain is optional and a no-op by default; it
ships no package-provided concrete initializer.

Importing this package must not load Typer/Rich, the Camoufox adapter, or
Playwright. No interaction behavior is implemented here.
"""

from __future__ import annotations

from sightstalker.ops.dependencies import EngineFactory
from sightstalker.ops.initializers import (
    ContextInitializationScope,
    ContextInitializer,
    ContextInitializerChain,
)
from sightstalker.ops.plans import Plan, PlanResult
from sightstalker.ops.runs import ManagedRunResult, execute_managed_run
from sightstalker.ops.surface import RunSurface

__all__ = [
    "ContextInitializationScope",
    "ContextInitializer",
    "ContextInitializerChain",
    "EngineFactory",
    "ManagedRunResult",
    "Plan",
    "PlanResult",
    "RunSurface",
    "execute_managed_run",
]
