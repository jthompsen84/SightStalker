"""Local operator/developer CLI for SightStalker (CLI-RUNNER-1).

This package adds a narrow, local Typer command-line interface over the
already-accepted SightStalker service layers (engine, sessions, artifacts,
persistence, diagnostics). It is an operator surface, not a control plane:
there is no web/API server, no daemon, no scheduler, no interaction
simulation, and no retry/recovery behavior.

Import hygiene:
    Importing this package (and ``sightstalker.cli.main``) must not import any
    concrete browser adapter, browser package, or web framework. The Camoufox
    engine is resolved lazily, only inside ``sightstalker.cli.runtime`` command
    execution, after an operator invokes a browser command.
"""

from __future__ import annotations

__all__: list[str] = []
