"""ArtifactManager write/read tests (spec 13, 19)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from sightstalker.artifacts import (
    ArtifactExistsError,
    ArtifactManager,
    ArtifactPathError,
    ArtifactPaths,
)
from sightstalker.models import ArtifactRef


def _mgr(tmp_path: Path) -> ArtifactManager:
    paths = ArtifactPaths(tmp_path)
    paths.ensure_data_dir()
    return ArtifactManager(paths)


def test_write_bytes_creates_file(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = mgr.write_bytes(
        relative_path=Path("runs/r1/blob.bin"),
        artifact_type="diagnostic_bundle",
        data=b"\x00\x01\x02",
    )
    assert (tmp_path.resolve() / ref.relative_path).is_file()
    assert not ref.relative_path.is_absolute()


def test_write_bytes_ref_fields(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    data = b"hello world"
    ref = mgr.write_bytes(
        relative_path=Path("logs/run.log"),
        artifact_type="run_log",
        data=data,
    )
    assert ref.size_bytes == len(data)
    assert ref.hash_algorithm == "sha256"
    assert ref.artifact_type == "run_log"
    assert ref.mime_type == "text/plain"  # .log extension


def test_write_text(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = mgr.write_text(
        relative_path=Path("logs/run.txt"),
        artifact_type="run_log",
        text="line one\nline two",
    )
    assert mgr.read_text(ref) == "line one\nline two"


def test_write_with_explicit_artifact_id(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = mgr.write_bytes(
        relative_path=Path("r/a.zip"),
        artifact_type="trace",
        data=b"PK",
        artifact_id="art_custom_0123456789abcdef",
    )
    assert ref.artifact_id == "art_custom_0123456789abcdef"


def test_write_generates_valid_artifact_id(tmp_path: Path) -> None:
    from sightstalker.sessions.ids import validate_artifact_id

    mgr = _mgr(tmp_path)
    ref = mgr.write_bytes(
        relative_path=Path("r/a.zip"),
        artifact_type="trace",
        data=b"PK",
    )
    assert validate_artifact_id(ref.artifact_id) == ref.artifact_id


def test_write_rejects_malformed_explicit_id(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    with pytest.raises(ArtifactPathError):
        mgr.write_bytes(
            relative_path=Path("r/a.zip"),
            artifact_type="trace",
            data=b"PK",
            artifact_id="not a valid id!",  # type: ignore[arg-type]
        )


def test_write_rejects_unknown_type(tmp_path: Path) -> None:
    from sightstalker.artifacts import UnsupportedArtifactTypeError

    mgr = _mgr(tmp_path)
    with pytest.raises(UnsupportedArtifactTypeError):
        mgr.write_bytes(
            relative_path=Path("r/a.bin"),
            artifact_type="bogus",  # type: ignore[arg-type]
            data=b"x",
        )


def test_no_overwrite(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    mgr.write_bytes(
        relative_path=Path("r/a.bin"),
        artifact_type="diagnostic_bundle",
        data=b"first",
    )
    with pytest.raises(ArtifactExistsError):
        mgr.write_bytes(
            relative_path=Path("r/a.bin"),
            artifact_type="diagnostic_bundle",
            data=b"second",
        )
    # Original content intact.
    assert (tmp_path.resolve() / "r" / "a.bin").read_bytes() == b"first"


def test_read_bytes_round_trip(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    data = bytes(range(256))
    ref = mgr.write_bytes(
        relative_path=Path("r/a.bin"),
        artifact_type="diagnostic_bundle",
        data=data,
    )
    assert mgr.read_bytes(ref) == data


def test_resolve_returns_absolute(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    ref = mgr.write_bytes(
        relative_path=Path("r/a.bin"),
        artifact_type="diagnostic_bundle",
        data=b"x",
    )
    resolved = mgr.resolve(ref)
    assert resolved.is_absolute()
    assert resolved == (tmp_path.resolve() / "r" / "a.bin")


def test_file_mode_best_effort(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions not enforced")
    mgr = _mgr(tmp_path)
    ref = mgr.write_bytes(
        relative_path=Path("r/a.bin"),
        artifact_type="diagnostic_bundle",
        data=b"x",
    )
    mode = (tmp_path.resolve() / ref.relative_path).stat().st_mode & 0o777
    assert mode == 0o600


def test_concurrent_same_target_one_winner(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    # Pre-create the parent dir to remove that race from the test.
    (tmp_path / "r").mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            mgr.write_bytes(
                relative_path=Path("r/contended.bin"),
                artifact_type="diagnostic_bundle",
                data=f"writer-{i}".encode(),
            )
            results.append("ok")
        except ArtifactExistsError:
            errors.append(ArtifactExistsError())
        except BaseException as exc:  # pragma: no cover - unexpected
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 1
    assert len(errors) == 7
    assert all(isinstance(e, ArtifactExistsError) for e in errors)


def test_write_into_symlinked_parent_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data"
    try:
        outside = tmp_path / "outside"
        outside.mkdir(exist_ok=True)
        ArtifactPaths(root).ensure_data_dir()
        link = root / "linked"
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("no symlink support")
    mgr = ArtifactManager(ArtifactPaths(root))
    with pytest.raises(ArtifactPathError):
        mgr.write_bytes(
            relative_path=Path("linked") / "a.bin",
            artifact_type="diagnostic_bundle",
            data=b"x",
        )


def test_read_validates_malformed_construct(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    # model_construct bypasses validation; manager must still reject.
    bad = ArtifactRef.model_construct(
        artifact_id="not valid",
        artifact_type="diagnostic_bundle",
        relative_path=Path("/abs/escape.bin"),
        sha256="zz",
        size_bytes=-1,
        mime_type="application/zip",
        hash_algorithm="sha256",
    )
    with pytest.raises(ArtifactPathError):
        mgr.read_bytes(bad)
