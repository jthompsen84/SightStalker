"""ArtifactManager JSON tests (spec 13.5, 19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sightstalker.artifacts import ArtifactError, ArtifactManager, ArtifactPaths


def _mgr(tmp_path: Path) -> ArtifactManager:
    paths = ArtifactPaths(tmp_path)
    paths.ensure_data_dir()
    return ArtifactManager(paths)


def test_write_json_round_trip(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    payload = {"b": 2, "a": 1, "nested": {"y": [1, 2, 3], "x": "v"}}
    ref = mgr.write_json(
        relative_path=Path("p/data.json"),
        artifact_type="fingerprint_profile",
        payload=payload,
    )
    assert mgr.read_json(ref) == payload


def test_write_json_no_trailing_newline(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = mgr.write_json(
        relative_path=Path("p/data.json"),
        artifact_type="fingerprint_profile",
        payload={"k": "v"},
    )
    raw = (tmp_path.resolve() / ref.relative_path).read_bytes()
    assert not raw.endswith(b"\n")


def test_write_json_deterministic_bytes(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    payload = {"z": 1, "a": {"d": 4, "c": 3}}
    ref1 = mgr.write_json(
        relative_path=Path("p/one.json"),
        artifact_type="fingerprint_profile",
        payload=payload,
    )
    ref2 = mgr.write_json(
        relative_path=Path("p/two.json"),
        artifact_type="fingerprint_profile",
        payload=payload,
    )
    # Sorted keys + compact separators → identical bytes → identical hash.
    assert ref1.sha256 == ref2.sha256


def test_write_json_expected_compact_form(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = mgr.write_json(
        relative_path=Path("p/c.json"),
        artifact_type="fingerprint_profile",
        payload={"b": 1, "a": 2},
    )
    raw = (tmp_path.resolve() / ref.relative_path).read_bytes()
    assert raw == b'{"a":2,"b":1}'


def test_write_json_rejects_nan(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    with pytest.raises(ArtifactError):
        mgr.write_json(
            relative_path=Path("p/nan.json"),
            artifact_type="fingerprint_profile",
            payload={"x": float("nan")},
        )


def test_write_json_rejects_infinity(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    with pytest.raises(ArtifactError):
        mgr.write_json(
            relative_path=Path("p/inf.json"),
            artifact_type="fingerprint_profile",
            payload={"x": float("inf")},
        )


def test_write_json_unicode_byte_length(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    # "é" is 2 UTF-8 bytes; ensure_ascii=False keeps it raw.
    payload = {"name": "café résumé 日本語"}
    ref = mgr.write_json(
        relative_path=Path("p/u.json"),
        artifact_type="fingerprint_profile",
        payload=payload,
    )
    raw = (tmp_path.resolve() / ref.relative_path).read_bytes()
    assert ref.size_bytes == len(raw)
    assert ref.size_bytes != len(raw.decode("utf-8"))  # bytes > chars


def test_read_json_parse_failure_raises_integrity(tmp_path: Path) -> None:
    from sightstalker.artifacts import ArtifactIntegrityError
    from sightstalker.artifacts.hashing import compute_sha256
    from sightstalker.models import ArtifactRef

    mgr = _mgr(tmp_path)
    # Write invalid JSON bytes directly, then build a matching ref.
    (tmp_path / "p").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "p" / "bad.json"
    payload = b"{not json"
    target.write_bytes(payload)
    ref = ArtifactRef(
        artifact_id="art_bad_0123456789abcdef",
        artifact_type="fingerprint_profile",
        relative_path=Path("p/bad.json"),
        sha256=compute_sha256(payload),
        size_bytes=len(payload),
        mime_type="application/json",
    )
    with pytest.raises(ArtifactIntegrityError):
        mgr.read_json(ref)
