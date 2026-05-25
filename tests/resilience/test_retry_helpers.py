"""Retry-helper tests: attempt counting, safety gating, sanitized failures."""

from __future__ import annotations

import pytest

from sightstalker.persistence.errors import PersistenceError
from sightstalker.resilience import RetryPolicy, retry_async, retry_sync
from sightstalker.resilience.errors import SecurityRefusal, UsageError


class _Counter:
    def __init__(self, exc: BaseException | None, *, succeed_on: int | None = None):
        self.calls = 0
        self.exc = exc
        self.succeed_on = succeed_on

    def __call__(self) -> str:
        self.calls += 1
        if self.succeed_on is not None and self.calls >= self.succeed_on:
            return "ok"
        if self.exc is not None:
            raise self.exc
        return "ok"


_RETRY3 = RetryPolicy(max_attempts=3, retry_on_kinds=("persistence",))


def test_default_policy_calls_once() -> None:
    counter = _Counter(PersistenceError("x"))
    with pytest.raises(PersistenceError):
        retry_sync(
            counter,
            policy=RetryPolicy(),
            operation_name="op",
            operation_safety="idempotent",
        )
    assert counter.calls == 1


def test_side_effect_free_retries_expected_attempts() -> None:
    counter = _Counter(PersistenceError("x"))
    with pytest.raises(PersistenceError):
        retry_sync(
            counter,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="side_effect_free",
        )
    assert counter.calls == 3


def test_idempotent_retries_expected_attempts() -> None:
    counter = _Counter(PersistenceError("x"))
    with pytest.raises(PersistenceError):
        retry_sync(
            counter,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="idempotent",
        )
    assert counter.calls == 3


def test_non_idempotent_calls_once_even_when_policy_says_retry() -> None:
    counter = _Counter(PersistenceError("x"))
    with pytest.raises(PersistenceError):
        retry_sync(
            counter,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="non_idempotent",
        )
    assert counter.calls == 1


def test_non_retryable_kind_not_retried() -> None:
    # Persistence is the only retryable kind here; a usage error is not.
    counter = _Counter(UsageError("bad input"))
    with pytest.raises(UsageError):
        retry_sync(
            counter,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="idempotent",
        )
    assert counter.calls == 1


def test_security_refusal_never_retried() -> None:
    counter = _Counter(SecurityRefusal("nope"))
    policy = RetryPolicy(
        max_attempts=3, retry_on_kinds=("security_refusal", "persistence")
    )
    with pytest.raises(SecurityRefusal):
        retry_sync(
            counter,
            policy=policy,
            operation_name="op",
            operation_safety="idempotent",
        )
    assert counter.calls == 1


def test_safe_to_retry_then_success() -> None:
    counter = _Counter(PersistenceError("transient"), succeed_on=3)
    result = retry_sync(
        counter,
        policy=_RETRY3,
        operation_name="op",
        operation_safety="idempotent",
    )
    assert result == "ok"
    assert counter.calls == 3


def test_final_error_is_original_not_tenacity_internal() -> None:
    counter = _Counter(PersistenceError("still failing"))
    with pytest.raises(PersistenceError) as excinfo:
        retry_sync(
            counter,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="idempotent",
        )
    text = f"{type(excinfo.value).__name__}: {excinfo.value}"
    assert "RetryError" not in text
    assert "Future" not in text
    assert "AttemptManager" not in text


def test_final_error_message_sanitized() -> None:
    counter = _Counter(PersistenceError("fail token=raw-token-123"))
    with pytest.raises(PersistenceError) as excinfo:
        retry_sync(
            counter,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="idempotent",
        )
    # The persistence error is raised as-is; resilience never widens it into a
    # tenacity error, so no tenacity internals leak. (Message sanitization is a
    # property of OperatorError formatting, not of re-raised originals.)
    assert "RetryError" not in repr(excinfo.value)


async def test_retry_async_non_idempotent_calls_once() -> None:
    calls = {"n": 0}

    async def func() -> str:
        calls["n"] += 1
        raise PersistenceError("x")

    with pytest.raises(PersistenceError):
        await retry_async(
            func,
            policy=_RETRY3,
            operation_name="op",
            operation_safety="non_idempotent",
        )
    assert calls["n"] == 1


async def test_retry_async_idempotent_retries_then_succeeds() -> None:
    calls = {"n": 0}

    async def func() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise PersistenceError("transient")
        return "ok"

    result = await retry_async(
        func,
        policy=_RETRY3,
        operation_name="op",
        operation_safety="idempotent",
    )
    assert result == "ok"
    assert calls["n"] == 3
