"""Session-state lifecycle layer for SightStalker.

This package owns the profile / session / run / context lifecycle, including
file-locked single-active-run enforcement and immutable storage-state
snapshots. It deliberately avoids importing any browser-engine, web-framework,
or logging dependencies so that the lifecycle surface stays portable and
cheaply importable.
"""

from sightstalker.sessions.errors import (
    SessionLifecycleError,
    SessionStateError,
)
from sightstalker.sessions.ids import (
    new_artifact_id,
    new_context_id,
    new_run_id,
)
from sightstalker.sessions.locks import (
    ProfileLockHandle,
    ProfileLockManager,
    ProfileLockUnavailable,
)
from sightstalker.sessions.manager import (
    ManagedSessionContext,
    SessionLifecycleResult,
    SessionManager,
)
from sightstalker.sessions.paths import (
    SessionPaths,
)
from sightstalker.sessions.state_store import (
    BrowserStateStore,
)

__all__ = [
    "BrowserStateStore",
    "ManagedSessionContext",
    "ProfileLockHandle",
    "ProfileLockManager",
    "ProfileLockUnavailable",
    "SessionLifecycleError",
    "SessionLifecycleResult",
    "SessionManager",
    "SessionPaths",
    "SessionStateError",
    "new_artifact_id",
    "new_context_id",
    "new_run_id",
]
