"""Retry-policy model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sightstalker.resilience import RetryPolicy


def test_default_policy_is_single_attempt() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 1
    assert policy.retry_on_kinds == ()
    assert policy.initial_delay_seconds == 0.0


def test_policy_is_frozen() -> None:
    policy = RetryPolicy()
    with pytest.raises(ValidationError):
        policy.max_attempts = 5  # type: ignore[misc]


def test_max_attempts_bounds() -> None:
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=11)


def test_negative_delays_rejected() -> None:
    with pytest.raises(ValidationError):
        RetryPolicy(initial_delay_seconds=-1.0)
    with pytest.raises(ValidationError):
        RetryPolicy(jitter_seconds=-1.0)


def test_retry_on_kinds_accepts_valid_kinds() -> None:
    policy = RetryPolicy(max_attempts=3, retry_on_kinds=("persistence", "external"))
    assert policy.retry_on_kinds == ("persistence", "external")
