"""Passive diagnostics services for SightStalker.

Screenshots, traces, console capture, and health records built on the accepted
engine protocols (``sightstalker.engines.base``), the ``ArtifactManager``, and
optional injected repository-like persistence dependencies.

These services are passive: they observe already-open browser handles and
produce artifacts/metadata. They never launch browsers, navigate, interact,
retry, recover, or expose CLI/web surfaces. Importing this package must not
import concrete browser adapter modules, browser packages, or SQLAlchemy/Alembic.

Diagnostic artifacts are sensitive by default; treat the data directory as
sensitive material.
"""

from sightstalker.diagnostics.console import (
    ConsoleCaptureHandle,
    ConsoleCaptureService,
)
from sightstalker.diagnostics.errors import (
    DiagnosticCaptureError,
    DiagnosticError,
    DiagnosticPersistenceError,
    DiagnosticUnsupportedError,
)
from sightstalker.diagnostics.health import HealthService
from sightstalker.diagnostics.models import (
    ConsoleEventRecord,
    DiagnosticArtifactResult,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    ScreenshotOptions,
    TraceOptions,
)
from sightstalker.diagnostics.paths import DiagnosticPathPolicy
from sightstalker.diagnostics.recorder import DiagnosticArtifactRecorder
from sightstalker.diagnostics.screenshot import ScreenshotService
from sightstalker.diagnostics.tracing import TraceCaptureHandle, TraceService

__all__ = [
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
]
