"""Reusable artifact manager for SightStalker.

This package generalizes the hardened storage-state file behavior from
SESSION-STATE-1 into a reusable artifact layer: safe path resolution,
no-overwrite exclusive writes, SHA-256/size verification, MIME provenance, and
``ArtifactRef`` references. It depends only on the contract models and the
neutral ``sightstalker.ids`` module — never on ``sightstalker.sessions`` — so it
can be reused by persistence, diagnostics, and other layers without cycles.
"""

from sightstalker.artifacts.errors import (
    ArtifactError,
    ArtifactExistsError,
    ArtifactIntegrityError,
    ArtifactPathError,
    UnsupportedArtifactTypeError,
)
from sightstalker.artifacts.hashing import compute_file_sha256, compute_sha256
from sightstalker.artifacts.manager import ArtifactManager
from sightstalker.artifacts.mime import (
    infer_mime_type,
    mime_type_for_artifact_type,
)
from sightstalker.artifacts.paths import ArtifactPaths

__all__ = [
    "ArtifactError",
    "ArtifactExistsError",
    "ArtifactIntegrityError",
    "ArtifactManager",
    "ArtifactPathError",
    "ArtifactPaths",
    "UnsupportedArtifactTypeError",
    "compute_file_sha256",
    "compute_sha256",
    "infer_mime_type",
    "mime_type_for_artifact_type",
]
