"""Diagnostic path policy tests (spec §11)."""

from __future__ import annotations

import pytest

from sightstalker.diagnostics import DiagnosticPathPolicy
from sightstalker.diagnostics.errors import DiagnosticCaptureError


def test_run_scoped_layout() -> None:
    policy = DiagnosticPathPolicy()
    p = policy.artifact_relative_path(
        artifact_id="art_screenshot_0123456789abcdef",
        kind="screenshot",
        suffix="screenshot.png",
        run_id="run_auto_0123456789abcdef",
    )
    parts = p.as_posix()
    assert parts == (
        "diagnostics/runs/run_auto_0123456789abcdef/"
        "art_screenshot_0123456789abcdef.screenshot.png"
    )


def test_unscoped_layout() -> None:
    policy = DiagnosticPathPolicy()
    p = policy.artifact_relative_path(
        artifact_id="art_trace_0123456789abcdef",
        kind="trace",
        suffix="trace.zip",
        run_id=None,
    )
    assert p.as_posix() == (
        "diagnostics/unscoped/art_trace_0123456789abcdef.trace.zip"
    )


def test_path_includes_artifact_id() -> None:
    policy = DiagnosticPathPolicy()
    p = policy.artifact_relative_path(
        artifact_id="art_console_abcdef0123456789",
        kind="console",
        suffix="console.jsonl",
    )
    assert "art_console_abcdef0123456789" in p.as_posix()


def test_path_is_relative() -> None:
    policy = DiagnosticPathPolicy()
    p = policy.artifact_relative_path(
        artifact_id="art_screenshot_0123456789abcdef",
        kind="screenshot",
        suffix="screenshot.png",
    )
    assert not p.is_absolute()


def test_screenshot_suffix_must_be_png() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("screenshot", "shot.jpg")


def test_trace_suffix_must_be_zip() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("trace", "trace.tar")


def test_console_suffix_must_be_jsonl() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("console", "console.json")


def test_suffix_rejects_path_separators() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("screenshot", "sub/dir.png")
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("screenshot", "sub\\dir.png")


def test_suffix_rejects_traversal() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("trace", "..zip")


def test_suffix_rejects_empty() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("screenshot", "")


def test_unknown_kind_rejected() -> None:
    with pytest.raises(DiagnosticCaptureError):
        DiagnosticPathPolicy.validate_suffix("video", "x.mp4")


def test_valid_suffix_passthrough() -> None:
    assert (
        DiagnosticPathPolicy.validate_suffix("screenshot", "failure.screenshot.png")
        == "failure.screenshot.png"
    )
