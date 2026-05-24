"""
sightstalker.diagnostics.errors — diagnostics exception hierarchy.

All diagnostic errors are sanitized: messages must never include diagnostic
bytes, console payloads, cookies, tokens, headers, raw storage state, absolute
temp paths, native object reprs, or absolute artifact paths.
"""

from __future__ import annotations


class DiagnosticError(RuntimeError):
    """Base class for diagnostics-layer failures."""


class DiagnosticCaptureError(DiagnosticError):
    """Raised when a passive capture cannot be completed."""


class DiagnosticPersistenceError(DiagnosticError):
    """Raised when optional metadata/health persistence fails."""


class DiagnosticUnsupportedError(DiagnosticError):
    """Raised when a requested diagnostic feature is not supported."""
