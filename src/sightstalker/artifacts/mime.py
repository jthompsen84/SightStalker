"""
sightstalker.artifacts.mime — MIME type policy for artifacts.

MIME on an ``ArtifactRef`` is provenance metadata, not a content sniff. There
is intentionally no ``python-magic`` dependency. Resolution precedence is:

    1. explicit MIME, if syntactically valid and type-compatible
    2. known file extension (refined against the type's compatibility set)
    3. artifact-type default

An explicit MIME that is incompatible with the artifact type raises
``UnsupportedArtifactTypeError``. An unknown artifact type is also rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

from sightstalker.artifacts.errors import UnsupportedArtifactTypeError
from sightstalker.models import ArtifactType

# Per-type default MIME.
_DEFAULT_MIME: dict[ArtifactType, str] = {
    "storage_state_initial": "application/json",
    "storage_state_final": "application/json",
    "fingerprint_profile": "application/json",
    "run_log": "application/x-jsonlines",
    "screenshot": "image/png",
    "trace": "application/zip",
    "diagnostic_bundle": "application/zip",
}

# Per-type allowlist of acceptable MIME values (defaults always included).
_COMPATIBLE_MIME: dict[ArtifactType, frozenset[str]] = {
    "storage_state_initial": frozenset({"application/json"}),
    "storage_state_final": frozenset({"application/json"}),
    "fingerprint_profile": frozenset({"application/json"}),
    "run_log": frozenset({"application/x-jsonlines", "text/plain"}),
    "screenshot": frozenset({"image/png", "image/jpeg"}),
    "trace": frozenset({"application/zip"}),
    "diagnostic_bundle": frozenset({"application/zip"}),
}

# Recognized file-extension refinements.
_EXTENSION_MIME: dict[str, str] = {
    ".json": "application/json",
    ".jsonl": "application/x-jsonlines",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".zip": "application/zip",
    ".txt": "text/plain",
    ".log": "text/plain",
}

# Conservative ``type/subtype`` syntactic validity check (RFC-ish, no params).
_MIME_SYNTAX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$")


def _require_known_type(artifact_type: ArtifactType) -> None:
    if artifact_type not in _DEFAULT_MIME:
        raise UnsupportedArtifactTypeError("unknown artifact type")


def is_valid_mime_syntax(value: str) -> bool:
    """Return True if ``value`` is a syntactically valid ``type/subtype``."""
    return bool(_MIME_SYNTAX_RE.match(value))


def mime_type_for_artifact_type(artifact_type: ArtifactType) -> str:
    """Return the default MIME type for ``artifact_type``."""
    _require_known_type(artifact_type)
    return _DEFAULT_MIME[artifact_type]


def _compatible(artifact_type: ArtifactType, mime: str) -> bool:
    return mime in _COMPATIBLE_MIME[artifact_type]


def infer_mime_type(
    artifact_type: ArtifactType,
    relative_path: Path,
    *,
    explicit: str | None = None,
) -> str:
    """Resolve the MIME type for an artifact.

    Precedence: explicit (valid + compatible) → known extension (if compatible)
    → artifact-type default. An incompatible explicit MIME raises
    ``UnsupportedArtifactTypeError``; an unknown artifact type is rejected.
    """
    _require_known_type(artifact_type)

    if explicit is not None:
        candidate = explicit.strip().lower()
        if not is_valid_mime_syntax(candidate):
            raise UnsupportedArtifactTypeError(
                "explicit MIME type is not syntactically valid"
            )
        if not _compatible(artifact_type, candidate):
            raise UnsupportedArtifactTypeError(
                "explicit MIME type is incompatible with the artifact type"
            )
        return candidate

    suffix = relative_path.suffix.lower()
    if suffix in _EXTENSION_MIME:
        ext_mime = _EXTENSION_MIME[suffix]
        if _compatible(artifact_type, ext_mime):
            return ext_mime

    return _DEFAULT_MIME[artifact_type]
