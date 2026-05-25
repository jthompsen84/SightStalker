"""Unit tests for the context initializer chain and scope.

Covers shallow immutability, empty-chain no-op, ordered sequential execution
proven with async event ordering, the no-rollback contract, and exception
pass-through (the chain does not catch).
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, cast

import pytest

from sightstalker.ops import (
    ContextInitializationScope,
    ContextInitializer,
    ContextInitializerChain,
)


def _scope() -> ContextInitializationScope:
    # Trusted runtime scope; fields are opaque sentinels for unit-level tests.
    return ContextInitializationScope(
        context=cast(Any, object()),
        profile=cast(Any, object()),
        session=cast(Any, object()),
        request=cast(Any, object()),
        resolution=cast(Any, object()),
    )


async def test_empty_chain_is_noop() -> None:
    chain = ContextInitializerChain()
    assert chain.initializers == ()
    await chain.initialize(_scope())  # must not raise or touch scope


async def test_single_initializer_called_with_scope() -> None:
    seen: list[ContextInitializationScope] = []

    class _Init:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            seen.append(scope)

    scope = _scope()
    await ContextInitializerChain((_Init(),)).initialize(scope)
    assert seen == [scope]


async def test_initializers_run_in_tuple_order_sequentially() -> None:
    events: list[str] = []
    a_done = asyncio.Event()

    class _A:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            events.append("a-start")
            # Yield control; B must NOT start during this await.
            await asyncio.sleep(0.01)
            events.append("a-end")
            a_done.set()

    class _B:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            # Prove A fully completed before B starts (sequential, not parallel).
            assert a_done.is_set(), "B started before A completed"
            events.append("b-start")
            events.append("b-end")

    await ContextInitializerChain((_A(), _B())).initialize(_scope())
    assert events == ["a-start", "a-end", "b-start", "b-end"]


async def test_chain_does_not_catch_exceptions() -> None:
    class _Boom:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await ContextInitializerChain((_Boom(),)).initialize(_scope())


async def test_no_rollback_first_runs_before_second_fails() -> None:
    ran: list[str] = []

    class _Ok:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            ran.append("ok")

    class _Boom:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            ran.append("boom-start")
            raise ValueError("second fails")

    with pytest.raises(ValueError):
        await ContextInitializerChain((_Ok(), _Boom())).initialize(_scope())
    # First initializer already ran and is not undone (no rollback).
    assert ran == ["ok", "boom-start"]


def test_scope_is_frozen_shallow() -> None:
    scope = _scope()
    with pytest.raises(dataclasses.FrozenInstanceError):
        scope.context = object()  # type: ignore[misc]


def test_chain_exposes_initializers_tuple() -> None:
    class _Init:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            return None

    init = _Init()
    chain = ContextInitializerChain((init,))
    assert chain.initializers == (init,)


def test_protocol_is_runtime_checkable() -> None:
    class _Init:
        async def initialize(self, scope: ContextInitializationScope) -> None:
            return None

    assert isinstance(_Init(), ContextInitializer)
    assert not isinstance(object(), ContextInitializer)
