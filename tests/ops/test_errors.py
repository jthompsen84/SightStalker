"""Tests for sightstalker.ops.errors.OpsPersistenceFailure."""

from __future__ import annotations

from sightstalker.ops.errors import OpsPersistenceFailure
from sightstalker.resilience import classify_exception
from sightstalker.resilience.errors import PersistenceFailure


def test_is_persistence_failure_subclass() -> None:
    assert issubclass(OpsPersistenceFailure, PersistenceFailure)


def test_carries_warnings() -> None:
    exc = OpsPersistenceFailure("boom", warnings=("orphan files remain",))
    assert exc.warnings == ("orphan files remain",)


def test_default_warnings_empty() -> None:
    exc = OpsPersistenceFailure("boom")
    assert exc.warnings == ()


def test_maps_to_public_persistence_error_label() -> None:
    exc = OpsPersistenceFailure("metadata persistence failed", warnings=("x",))
    operator = classify_exception(exc)
    assert operator.type == "PersistenceError"
    assert operator.kind == "persistence"
    assert operator.exit_code == 3


def test_message_sanitized() -> None:
    exc = OpsPersistenceFailure("failed access_token=raw-token-123")
    assert "raw-token-123" not in exc.message
