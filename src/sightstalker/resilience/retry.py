"""
sightstalker.resilience.retry — conservative, operation-safety-gated retries.

This module provides retry *primitives* built on tenacity. RESILIENCE-1 does
not apply them to any existing workflow (browser navigation, artifact writes,
DB mutations, diagnostic capture all remain single-attempt).

Hard safety gates:
- the default :class:`RetryPolicy` performs no retries (``max_attempts == 1``);
- ``operation_safety == "non_idempotent"`` => exactly one attempt, always,
  regardless of policy;
- retries happen only when the classified error ``kind`` is listed in
  ``policy.retry_on_kinds``;
- ``security_refusal`` / ``usage`` / ``configuration`` kinds are never retried;
- tenacity runs with ``reraise=True`` so the final failure is the original
  exception -- no ``RetryError`` / attempt-object / function repr ever leaks.

tenacity is imported lazily inside the retry functions so that importing this
module does not import tenacity at module load.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from pydantic import Field

from sightstalker.models import ToolkitModel
from sightstalker.resilience.classification import classify_exception
from sightstalker.resilience.models import ErrorKind

if TYPE_CHECKING:
    from tenacity import RetryCallState

OperationSafety = Literal["side_effect_free", "idempotent", "non_idempotent"]

T = TypeVar("T")

# Kinds that must never be retried regardless of policy.
_NEVER_RETRY_KINDS: frozenset[ErrorKind] = frozenset(
    {"security_refusal", "usage", "configuration"}
)


class RetryPolicy(ToolkitModel):
    """Declarative retry policy. Defaults to a single attempt (no retry)."""

    max_attempts: int = Field(default=1, ge=1, le=10)
    initial_delay_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    max_delay_seconds: float = Field(default=0.0, ge=0.0, le=600.0)
    jitter_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    retry_on_kinds: tuple[ErrorKind, ...] = ()


def _effective_attempts(policy: RetryPolicy, operation_safety: OperationSafety) -> int:
    """Return the number of attempts allowed under policy + safety gating."""
    if operation_safety == "non_idempotent":
        return 1
    if policy.max_attempts <= 1:
        return 1
    if not policy.retry_on_kinds:
        return 1
    return policy.max_attempts


def _is_retryable_exception(exc: BaseException, policy: RetryPolicy) -> bool:
    """Decide whether ``exc`` is retryable under ``policy``."""
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    try:
        operator = classify_exception(exc)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - if classification fails, do not retry
        return False
    if operator.kind in _NEVER_RETRY_KINDS:
        return False
    return operator.kind in policy.retry_on_kinds


def _build_wait(policy: RetryPolicy) -> Any:
    """Build a tenacity wait strategy from the policy (bounded, optional jitter)."""
    from tenacity import wait_exponential, wait_none, wait_random

    if policy.initial_delay_seconds <= 0.0 and policy.jitter_seconds <= 0.0:
        return wait_none()

    max_wait = (
        policy.max_delay_seconds
        if policy.max_delay_seconds > 0.0
        else max(policy.initial_delay_seconds, 1.0) * 60.0
    )
    wait: Any = wait_exponential(
        multiplier=max(policy.initial_delay_seconds, 0.0),
        max=max_wait,
    )
    if policy.jitter_seconds > 0.0:
        wait = wait + wait_random(0.0, policy.jitter_seconds)
    return wait


def _make_retry_predicate(policy: RetryPolicy) -> Callable[["RetryCallState"], bool]:
    """Return a tenacity retry predicate over the classified error kind."""

    def _predicate(retry_state: "RetryCallState") -> bool:
        outcome = retry_state.outcome
        if outcome is None or not outcome.failed:
            return False
        exc = outcome.exception()
        if exc is None:
            return False
        return _is_retryable_exception(exc, policy)

    return _predicate


def retry_sync(
    func: Callable[[], T],
    *,
    policy: RetryPolicy,
    operation_name: str,
    operation_safety: OperationSafety,
) -> T:
    """Run ``func`` with bounded retries under ``policy`` and safety gating.

    The final failure is re-raised as the original exception (tenacity
    ``reraise=True``); no tenacity internals are exposed.
    """
    from tenacity import Retrying, stop_after_attempt

    attempts = _effective_attempts(policy, operation_safety)
    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=_build_wait(policy),
        retry=_make_retry_predicate(policy),
        reraise=True,
    )
    return retryer(func)


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    operation_name: str,
    operation_safety: OperationSafety,
) -> T:
    """Async counterpart of :func:`retry_sync` (same safety gating)."""
    from tenacity import AsyncRetrying, stop_after_attempt

    attempts = _effective_attempts(policy, operation_safety)
    retryer = AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=_build_wait(policy),
        retry=_make_retry_predicate(policy),
        reraise=True,
    )
    async for attempt in retryer:
        with attempt:
            return await func()
    raise RuntimeError("retry_async exhausted without result")  # pragma: no cover


__all__ = [
    "OperationSafety",
    "RetryPolicy",
    "retry_async",
    "retry_sync",
]
