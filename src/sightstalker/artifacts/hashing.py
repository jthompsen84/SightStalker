"""
sightstalker.artifacts.hashing — SHA-256 + size helpers.

SHA-256 only. Digests are returned as lowercase hex. File hashing reads in
bounded chunks. Failures are surfaced as sanitized artifact errors that never
include the absolute path of the file being hashed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sightstalker.artifacts.errors import ArtifactIntegrityError

_DEFAULT_CHUNK_SIZE = 1024 * 1024


def compute_sha256(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path, *, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of the file at ``path``.

    Reads in bounded chunks. Missing or unreadable files raise a sanitized
    ``ArtifactIntegrityError`` that does not leak the absolute path.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        raise ArtifactIntegrityError(
            "artifact file could not be read for hashing"
        ) from None
    return digest.hexdigest()


def file_size(path: Path) -> int:
    """Return the byte size of the file at ``path``.

    Missing or unreadable files raise a sanitized ``ArtifactIntegrityError``.
    """
    try:
        return path.stat().st_size
    except OSError:
        raise ArtifactIntegrityError(
            "artifact file size could not be determined"
        ) from None
