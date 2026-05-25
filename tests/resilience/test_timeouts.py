"""Timeout-policy tests: defaults, bounds, and no runtime behavior change."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sightstalker.resilience import TimeoutPolicy
from sightstalker.resilience.classification import classify_exception


def test_defaults_are_valid() -> None:
    policy = TimeoutPolicy()
    assert policy.navigation_ms == 45_000
    assert policy.browser_launch_ms == 30_000
    assert policy.browser_context_ms == 30_000
    assert policy.diagnostics_ms == 30_000
    assert policy.database_ms == 30_000
    assert policy.artifact_io_ms == 30_000


def test_defaults_match_accepted_config_values() -> None:
    # Mirror accepted BrowserLaunchConfig / BrowserContextConfig defaults.
    from sightstalker.models import BrowserContextConfig, BrowserLaunchConfig

    launch = BrowserLaunchConfig()
    context = BrowserContextConfig()
    policy = TimeoutPolicy()
    assert policy.browser_launch_ms == launch.timeout_ms
    assert policy.navigation_ms == context.navigation_timeout_ms
    assert policy.browser_context_ms == context.default_timeout_ms


def test_too_low_value_rejected() -> None:
    with pytest.raises(ValidationError):
        TimeoutPolicy(navigation_ms=50)


def test_too_high_value_rejected() -> None:
    with pytest.raises(ValidationError):
        TimeoutPolicy(navigation_ms=3_600_001)


def test_policy_is_frozen() -> None:
    policy = TimeoutPolicy()
    with pytest.raises(ValidationError):
        policy.navigation_ms = 1000  # type: ignore[misc]


def test_timeout_classification_is_conservative() -> None:
    oe = classify_exception(TimeoutError("deadline exceeded"))
    assert oe.recoverability != "safe_to_retry"
