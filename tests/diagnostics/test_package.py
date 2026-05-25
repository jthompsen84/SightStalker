"""Package inclusion tests for diagnostics (spec §22 clean install)."""

from __future__ import annotations

import sightstalker
from sightstalker import diagnostics


def test_version_is_0_4_5() -> None:
    assert sightstalker.__version__ == "0.4.5"


def test_public_surface_exports() -> None:
    expected = {
        "ConsoleCaptureHandle",
        "ConsoleCaptureService",
        "ConsoleEventRecord",
        "DiagnosticArtifactRecorder",
        "DiagnosticArtifactResult",
        "DiagnosticCaptureError",
        "DiagnosticError",
        "DiagnosticPathPolicy",
        "DiagnosticPersistenceError",
        "DiagnosticPersistencePolicy",
        "DiagnosticTarget",
        "DiagnosticUnsupportedError",
        "HealthService",
        "ScreenshotOptions",
        "ScreenshotService",
        "TraceCaptureHandle",
        "TraceOptions",
        "TraceService",
    }
    assert set(diagnostics.__all__) == expected


def test_all_exports_resolve() -> None:
    for name in diagnostics.__all__:
        assert hasattr(diagnostics, name), f"missing export: {name}"
