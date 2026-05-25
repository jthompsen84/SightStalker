"""
sightstalker.ids — neutral identifier generation.

This module is the single, dependency-free source of identifier *generation*
for the package. It sits below both ``sightstalker.sessions`` and
``sightstalker.artifacts`` so that the artifact layer can mint artifact IDs
without importing the session layer (which would create a dependency cycle).

Only generation lives here. Runtime *validation* of identifiers against their
``StringConstraints`` patterns stays in the layer that owns path safety
(``sightstalker.sessions.ids`` re-exports validators), because validation is
coupled to path-component trust rather than to ID minting.

Generated forms (all satisfy the accepted identifier regex contracts):

    run_auto_<16 hex>
    ctx_auto_<12 hex>
    art_<safe-prefix>_<16 hex>
"""

from __future__ import annotations

import re
import secrets

from sightstalker.models import (
    ArtifactId,
    ContextId,
    ProfileId,
    RunId,
    SessionId,
)

_SAFE_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")

# Default fallback prefix for artifact IDs whose requested prefix sanitizes to
# nothing. "artifact" is the neutral, layer-agnostic default for this module.
_DEFAULT_ARTIFACT_PREFIX = "artifact"


def _safe_prefix(prefix: str, *, fallback: str = _DEFAULT_ARTIFACT_PREFIX) -> str:
    """
    Sanitize an artifact-id prefix to alphanumeric/underscore/hyphen only.

    - Disallowed characters are collapsed to underscores.
    - Leading underscores/hyphens are stripped.
    - An empty result falls back to ``fallback``.
    - The result is truncated so the final ``ArtifactId`` always satisfies its
      regex contract (``<= 16`` characters is safe).
    """
    cleaned = _SAFE_PREFIX_RE.sub("_", prefix.strip())
    cleaned = cleaned.lstrip("_-")
    cleaned = cleaned.strip()
    if not cleaned:
        return fallback
    return cleaned[:16]


def new_profile_id() -> ProfileId:
    """Generate a fresh ``ProfileId`` of the form ``prof_auto_<hex>``.

    Added for CLI-RUNNER-1 so the CLI can mint profile identities without
    importing the session layer. The result satisfies the accepted
    ``ProfileId`` regex contract.
    """
    return f"prof_auto_{secrets.token_hex(8)}"


def new_session_id() -> SessionId:
    """Generate a fresh ``SessionId`` of the form ``sess_auto_<hex>``.

    Added for CLI-RUNNER-1 so the CLI can mint session identities without
    importing the session layer. The result satisfies the accepted
    ``SessionId`` regex contract.
    """
    return f"sess_auto_{secrets.token_hex(8)}"


def new_run_id() -> RunId:
    """Generate a fresh ``RunId`` of the form ``run_auto_<hex>``."""
    return f"run_auto_{secrets.token_hex(8)}"


def new_context_id() -> ContextId:
    """Generate a fresh ``ContextId`` of the form ``ctx_auto_<hex>``."""
    return f"ctx_auto_{secrets.token_hex(6)}"


def new_artifact_id(prefix: str = "artifact") -> ArtifactId:
    """Generate a fresh ``ArtifactId`` of the form ``art_<safe-prefix>_<hex>``."""
    safe = _safe_prefix(prefix)
    return f"art_{safe}_{secrets.token_hex(8)}"


def safe_artifact_prefix(
    prefix: str, *, fallback: str = _DEFAULT_ARTIFACT_PREFIX
) -> str:
    """Public wrapper over the prefix sanitizer for cross-layer reuse.

    Exposed so ``sightstalker.sessions.ids`` can preserve its legacy ``"state"``
    fallback without re-implementing sanitization or reaching into a private
    name.
    """
    return _safe_prefix(prefix, fallback=fallback)
