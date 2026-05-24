"""
sightstalker.artifacts.errors — artifact-layer exception hierarchy.

All artifact errors are sanitized: messages must never include raw artifact
payloads, storage state, cookies, headers, tokens, secrets, or absolute
filesystem paths. Prefer stable reasons plus non-sensitive identifiers
(artifact ID, artifact type, relative path).
"""

from __future__ import annotations


class ArtifactError(RuntimeError):
    """Base class for all artifact-layer failures."""


class ArtifactPathError(ArtifactError):
    """Raised when an artifact path is unsafe, escaping, or non-conforming."""


class ArtifactExistsError(ArtifactError):
    """Raised when a write target already exists (no-overwrite policy)."""


class ArtifactIntegrityError(ArtifactError):
    """Raised when on-disk bytes fail size/hash verification or cannot be read."""


class UnsupportedArtifactTypeError(ArtifactError):
    """Raised for unknown artifact types or incompatible explicit MIME types."""
