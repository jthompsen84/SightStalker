"""
sightstalker.ops.initializers — trusted post-context/pre-page initializer seam.

This module defines the ordered, optional context-initializer chain composed by
``ops.execute_managed_run`` after ``BrowserRuntime.new_context()`` returns a
``BrowserContextHandle`` and before any plan creates or uses a page.

This is a **trusted executable seam, not a sandbox**. Caller-supplied
initializers are trusted programmatic code. CONTEXT-INITIALIZER-1 ships no
package-provided concrete initializer, performs no file/CLI/DB/remote loading,
and the chain itself never creates pages, navigates, injects scripts, starts
tracing, captures storage state, accesses native objects, or persists metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sightstalker.engines.base import BrowserContextHandle
from sightstalker.environment.models import ContextConfigResolution
from sightstalker.models.runs import RunRequest
from sightstalker.models.sessions import ProfileRecord, SessionRecord


@dataclass(frozen=True)
class ContextInitializationScope:
    """Runtime data available to trusted context initializers.

    Provided after context creation and before plan page usage. ``frozen=True``
    prevents field reassignment but is shallow: the live ``context`` handle is a
    trusted runtime object and is not capability-restricted. This scope is not a
    sandbox.

    ``session`` is the effective session used to open the context and
    ``resolution`` describes the exact effective launch/context config for this
    run. ``request.start_url`` is the redacted metadata URL, never a raw
    navigation URL. The scope intentionally excludes raw navigation URLs,
    repositories, ArtifactManager, data_dir, persistence sessions, and native
    browser/runtime objects. Initializers and chain code must not log or print
    ``profile``/``session``/``request``/``resolution`` wholesale.
    """

    context: BrowserContextHandle
    profile: ProfileRecord
    session: SessionRecord
    request: RunRequest
    resolution: ContextConfigResolution


@runtime_checkable
class ContextInitializer(Protocol):
    """Trusted async post-context/pre-page initializer.

    A trusted executable extension seam, not a sandbox. CONTEXT-INITIALIZER-1
    does not load initializers from files, CLI flags, DB rows, remote sources,
    or untrusted plugins, and ships no package-provided mutating initializer.
    """

    async def initialize(self, scope: ContextInitializationScope) -> None:
        ...


class ContextInitializerChain:
    """Ordered, sequential, no-rollback initializer chain.

    The empty chain is a no-op. Initializers run in tuple order, awaited one at a
    time — no parallelism, gather, scheduling, background tasks, or retry
    wrapping. The chain does not catch initializer exceptions; ops routes them
    through the managed-run cleanup path. The chain itself never calls page or
    context lifecycle/native methods.

    There is no rollback/compensation: if initializer N fails, initializers
    1..N-1 already ran and are not undone. Because this PR ships no
    package-provided mutating initializer, that creates no package-side partial
    state; any future mutating initializer must be idempotent or self-rollback
    and undergo dedicated review.
    """

    def __init__(self, initializers: tuple[ContextInitializer, ...] = ()) -> None:
        self._initializers = initializers

    @property
    def initializers(self) -> tuple[ContextInitializer, ...]:
        return self._initializers

    async def initialize(self, scope: ContextInitializationScope) -> None:
        for initializer in self._initializers:
            await initializer.initialize(scope)


__all__ = [
    "ContextInitializationScope",
    "ContextInitializer",
    "ContextInitializerChain",
]
