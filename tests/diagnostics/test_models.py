"""Diagnostic model tests (spec §10)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sightstalker.diagnostics import (
    ConsoleEventRecord,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    ScreenshotOptions,
    TraceOptions,
)


def test_target_defaults_all_none() -> None:
    t = DiagnosticTarget()
    assert t.session_id is None
    assert t.run_id is None
    assert t.context_id is None
    assert t.run_order is None


def test_target_run_order_nonnegative() -> None:
    DiagnosticTarget(run_order=0)
    with pytest.raises(ValidationError):
        DiagnosticTarget(run_order=-1)


def test_persistence_policy_defaults_false() -> None:
    p = DiagnosticPersistencePolicy()
    assert p.persist_artifact_metadata is False
    assert p.persist_health_record is False


def test_screenshot_options_defaults() -> None:
    o = ScreenshotOptions()
    assert o.full_page is False
    assert o.filename_suffix == "screenshot.png"


def test_trace_options_defaults() -> None:
    o = TraceOptions()
    assert o.filename_suffix == "trace.zip"


def test_console_event_timestamp_timezone_aware() -> None:
    e = ConsoleEventRecord(
        event_type="log",
        text_redacted="hello",
        location=None,
        timestamp=datetime.now(timezone.utc),
    )
    assert e.timestamp.tzinfo is not None


def test_models_are_frozen() -> None:
    t = DiagnosticTarget()
    with pytest.raises(ValidationError):
        t.run_order = 5  # type: ignore[misc]
