"""
sightstalker.sessions.errors — narrow local exceptions for the lifecycle layer.

These are intentionally minimal. SESSION-STATE-1 does not introduce a global
project error hierarchy; only the few exceptions needed by the session-state
lifecycle live here (and ``ProfileLockUnavailable`` lives in ``locks.py``).
"""

from __future__ import annotations


class SessionStateError(RuntimeError):
    """Invalid, missing, corrupt, or unsafe browser storage-state reference."""


class SessionLifecycleError(RuntimeError):
    """Unexpected lifecycle orchestration failure."""
