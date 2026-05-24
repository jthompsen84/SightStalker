"""
sightstalker.sessions.ids — identifier generation and runtime validation.

This module generates run/context/artifact identifiers that satisfy the
accepted identifier regex contracts, and provides runtime validation helpers
used by ``SessionPaths`` and ``BrowserStateStore`` before any externally
supplied identifier is used as a filesystem path component.

Type annotations alone are insufficient: the accepted identifier aliases are
``Annotated[str, StringConstraints(...)]``, which Pydantic enforces at model
boundaries but the interpreter does not enforce on raw ``str`` / ``cast`` input.
Path-component identifiers must therefore be validated at runtime.
"""

from __future__ import annotations

import secrets

from pydantic import TypeAdapter

from sightstalker.ids import new_context_id as _neutral_new_context_id
from sightstalker.ids import new_run_id as _neutral_new_run_id
from sightstalker.ids import safe_artifact_prefix as _neutral_safe_prefix
from sightstalker.models import (
    ArtifactId,
    ContextId,
    ProfileId,
    RunId,
    SessionId,
)

# ---------------------------------------------------------------------------
# Runtime validation adapters
# ---------------------------------------------------------------------------

_PROFILE_ID_ADAPTER: TypeAdapter[ProfileId] = TypeAdapter(ProfileId)
_RUN_ID_ADAPTER: TypeAdapter[RunId] = TypeAdapter(RunId)
_CONTEXT_ID_ADAPTER: TypeAdapter[ContextId] = TypeAdapter(ContextId)
_ARTIFACT_ID_ADAPTER: TypeAdapter[ArtifactId] = TypeAdapter(ArtifactId)
_SESSION_ID_ADAPTER: TypeAdapter[SessionId] = TypeAdapter(SessionId)


def validate_profile_id(value: object) -> ProfileId:
    """Validate and return a ``ProfileId``; raise on malformed input."""
    return _PROFILE_ID_ADAPTER.validate_python(value)


def validate_run_id(value: object) -> RunId:
    """Validate and return a ``RunId``; raise on malformed input."""
    return _RUN_ID_ADAPTER.validate_python(value)


def validate_context_id(value: object) -> ContextId:
    """Validate and return a ``ContextId``; raise on malformed input."""
    return _CONTEXT_ID_ADAPTER.validate_python(value)


def validate_artifact_id(value: object) -> ArtifactId:
    """Validate and return an ``ArtifactId``; raise on malformed input."""
    return _ARTIFACT_ID_ADAPTER.validate_python(value)


def validate_session_id(value: object) -> SessionId:
    """Validate and return a ``SessionId``; raise on malformed input."""
    return _SESSION_ID_ADAPTER.validate_python(value)


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------
#
# Generation is delegated to the neutral ``sightstalker.ids`` module so that
# the artifact layer can mint IDs without importing the session layer. The one
# behavioral difference preserved here is the session-layer fallback prefix:
# historically ``new_artifact_id("")`` produced ``art_state_...`` within the
# session-state store, and the state store relies on the ``"init"``/``"final"``
# prefixes it passes explicitly. We keep the legacy ``"state"`` fallback for
# this module's public helper to avoid changing any SESSION-STATE-1 behavior.


def _safe_prefix(prefix: str) -> str:
    """Session-layer prefix sanitizer (legacy ``"state"`` fallback)."""
    return _neutral_safe_prefix(prefix, fallback="state")


def new_run_id() -> RunId:
    """Generate a fresh ``RunId`` of the form ``run_auto_<hex>``."""
    return _neutral_new_run_id()


def new_context_id() -> ContextId:
    """Generate a fresh ``ContextId`` of the form ``ctx_auto_<hex>``."""
    return _neutral_new_context_id()


def new_artifact_id(prefix: str = "state") -> ArtifactId:
    """Generate a fresh ``ArtifactId`` of the form ``art_<safe-prefix>_<hex>``.

    Uses the session-layer ``"state"`` fallback to preserve SESSION-STATE-1
    behavior; ID minting itself is shared with ``sightstalker.ids``.
    """
    safe = _safe_prefix(prefix)
    return f"art_{safe}_{secrets.token_hex(8)}"
