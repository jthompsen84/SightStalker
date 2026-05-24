"""Artifact path-safety tests (spec 12, 19)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sightstalker.artifacts.errors import ArtifactPathError
from sightstalker.artifacts.paths import ArtifactPaths


def _supports_symlinks(tmp_path: Path) -> bool:
    try:
        t = tmp_path / "_t"
        t.mkdir()
        link = tmp_path / "_l"
        link.symlink_to(t)
        link.unlink()
        t.rmdir()
        return True
    except (OSError, NotImplementedError):
        return False


def test_ensure_data_dir_creates_when_missing(tmp_path: Path) -> None:
    root = tmp_path / "data"
    paths = ArtifactPaths(root)
    created = paths.ensure_data_dir()
    assert created.is_dir()


def test_ensure_data_dir_rejects_file_root(tmp_path: Path) -> None:
    root = tmp_path / "data_file"
    root.write_bytes(b"x")
    paths = ArtifactPaths(root)
    with pytest.raises(ArtifactPathError):
        paths.ensure_data_dir()


def test_data_dir_permissions_best_effort(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions not enforced")
    root = tmp_path / "data"
    paths = ArtifactPaths(root)
    paths.ensure_data_dir()
    assert (root.stat().st_mode & 0o777) == 0o700


def test_assert_safe_rejects_absolute(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    with pytest.raises(ArtifactPathError):
        paths.assert_safe_relative_path(Path("/etc/passwd"))


def test_assert_safe_rejects_empty(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    with pytest.raises(ArtifactPathError):
        paths.assert_safe_relative_path(Path(""))
    with pytest.raises(ArtifactPathError):
        paths.assert_safe_relative_path(Path("."))


def test_assert_safe_rejects_traversal(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    with pytest.raises(ArtifactPathError):
        paths.assert_safe_relative_path(Path("a/../../b"))
    with pytest.raises(ArtifactPathError):
        paths.assert_safe_relative_path(Path("..") / "b")


def test_assert_safe_rejects_nul(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    with pytest.raises(ArtifactPathError):
        paths.assert_safe_relative_path(Path("a\x00b/c.txt"))


def test_assert_safe_accepts_normal_relative(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    rel = paths.assert_safe_relative_path(Path("runs/r1/out.json"))
    assert rel == Path("runs/r1/out.json")


def test_resolve_relative_path_ok(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    paths.ensure_data_dir()
    resolved = paths.resolve_relative_path(Path("a/b.json"))
    assert resolved == (tmp_path.resolve() / "a" / "b.json")


def test_resolve_rejects_traversal(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    with pytest.raises(ArtifactPathError):
        paths.resolve_relative_path(Path("..") / "x")


def test_resolve_rejects_symlinked_parent(tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("no symlink support")
    root = tmp_path / "data"
    paths = ArtifactPaths(root)
    paths.ensure_data_dir()
    outside = tmp_path / "outside_dir"
    outside.mkdir(exist_ok=True)
    link = root / "linkdir"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactPathError):
        paths.resolve_relative_path(Path("linkdir") / "x.json")


def test_resolve_rejects_symlinked_target(tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("no symlink support")
    root = tmp_path / "data"
    paths = ArtifactPaths(root)
    paths.ensure_data_dir()
    outside = tmp_path / "secret.json"
    outside.write_bytes(b"{}")
    link = root / "ln.json"
    link.symlink_to(outside)
    with pytest.raises(ArtifactPathError):
        paths.resolve_relative_path(Path("ln.json"))


def test_resolve_rejects_nondir_parent(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    paths.ensure_data_dir()
    (tmp_path / "afile").write_bytes(b"x")
    with pytest.raises(ArtifactPathError):
        paths.resolve_relative_path(Path("afile") / "child.json")


def test_ensure_parent_dir_creates(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    parent = paths.ensure_parent_dir(Path("runs/r1/out.json"))
    assert parent.is_dir()
    assert parent == (tmp_path.resolve() / "runs" / "r1")


def test_relative_to_data_dir_rejects_outside(tmp_path: Path) -> None:
    root = tmp_path / "data"
    paths = ArtifactPaths(root)
    paths.ensure_data_dir()
    with pytest.raises(ArtifactPathError):
        paths.relative_to_data_dir(tmp_path / "x.json")


def test_path_exceptions_omit_absolute_root(tmp_path: Path) -> None:
    paths = ArtifactPaths(tmp_path)
    with pytest.raises(ArtifactPathError) as exc_info:
        paths.resolve_relative_path(Path("..") / "x")
    assert str(tmp_path) not in str(exc_info.value)
