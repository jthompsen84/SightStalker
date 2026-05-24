"""Hashing tests (spec 10, 19)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sightstalker.artifacts import compute_file_sha256, compute_sha256
from sightstalker.artifacts.errors import ArtifactIntegrityError
from sightstalker.artifacts.hashing import file_size


def test_compute_sha256_known_digest() -> None:
    assert compute_sha256(b"") == hashlib.sha256(b"").hexdigest()
    assert compute_sha256(b"hello") == hashlib.sha256(b"hello").hexdigest()


def test_compute_sha256_is_lowercase_hex() -> None:
    digest = compute_sha256(b"abc")
    assert digest == digest.lower()
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_compute_file_sha256_matches(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    payload = b"some bytes here" * 100
    f.write_bytes(payload)
    assert compute_file_sha256(f) == hashlib.sha256(payload).hexdigest()


def test_compute_file_sha256_chunked_matches_whole(tmp_path: Path) -> None:
    f = tmp_path / "big.bin"
    payload = bytes(range(256)) * 5000  # > 1 MiB
    f.write_bytes(payload)
    assert compute_file_sha256(f, chunk_size=4096) == hashlib.sha256(payload).hexdigest()


def test_compute_file_sha256_missing_raises_sanitized(tmp_path: Path) -> None:
    missing = tmp_path / "nope.bin"
    with pytest.raises(ArtifactIntegrityError) as exc_info:
        compute_file_sha256(missing)
    assert str(missing) not in str(exc_info.value)


def test_compute_file_sha256_rejects_nonpositive_chunk(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        compute_file_sha256(f, chunk_size=0)


def test_file_size_matches(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"12345")
    assert file_size(f) == 5


def test_file_size_missing_raises_sanitized(tmp_path: Path) -> None:
    missing = tmp_path / "nope.bin"
    with pytest.raises(ArtifactIntegrityError) as exc_info:
        file_size(missing)
    assert str(missing) not in str(exc_info.value)
