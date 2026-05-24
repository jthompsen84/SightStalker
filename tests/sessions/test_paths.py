"""Tests for sightstalker.sessions.paths (spec 21.3)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

from sightstalker.models import ProfileId, RunId
from sightstalker.sessions.paths import SessionPaths

_PROFILE = cast(ProfileId, "prof_alpha_default")
_RUN = cast(RunId, "run_auto_0123456789abcdef")


def _supports_symlinks(tmp_path: Path) -> bool:
    try:
        target = tmp_path / "_symlink_probe_target"
        target.mkdir()
        link = tmp_path / "_symlink_probe_link"
        link.symlink_to(target)
        link.unlink()
        target.rmdir()
        return True
    except (OSError, NotImplementedError):
        return False


def test_profile_dir_under_data_dir(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    profile_dir = paths.profile_dir(_PROFILE)
    assert profile_dir.is_relative_to(tmp_path.resolve())
    assert profile_dir.name == _PROFILE


def test_profile_lock_path_is_profile_scoped(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    lock_path = paths.profile_lock_path(_PROFILE)
    assert lock_path.parent == paths.profile_dir(_PROFILE)
    assert lock_path.name.endswith(".lock")


def test_run_dir_under_profile_runs(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    run_dir = paths.run_dir(_PROFILE, _RUN)
    assert run_dir.parent == paths.runs_dir(_PROFILE)
    assert run_dir.name == _RUN


def test_initial_path_filename(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    p = paths.storage_state_initial_path(_PROFILE, _RUN)
    assert p.name == "storage_state.initial.json"


def test_final_path_filename(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    p = paths.storage_state_final_path(_PROFILE, _RUN)
    assert p.name == "storage_state.final.json"


def test_relative_to_data_dir_returns_relative(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    target = paths.run_dir(_PROFILE, _RUN)
    rel = paths.relative_to_data_dir(target)
    assert not rel.is_absolute()
    assert (tmp_path.resolve() / rel) == target.resolve()


def test_relative_to_data_dir_rejects_outside(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    outside = tmp_path.parent / "elsewhere" / "x.json"
    with pytest.raises(ValueError):
        paths.relative_to_data_dir(outside)


def test_relative_to_data_dir_rejects_dotdot_escape(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    with pytest.raises(ValueError):
        paths.relative_to_data_dir(Path("..") / "escape.json")


def test_relative_to_data_dir_rejects_absolute_outside(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    with pytest.raises(ValueError):
        paths.relative_to_data_dir(Path("/etc/passwd"))


def test_relative_to_data_dir_rejects_symlink_inside(tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("platform does not support symlinks")
    paths = SessionPaths(tmp_path)
    root = tmp_path.resolve()
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    link = root / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        paths.relative_to_data_dir(link / "x.json")


def test_resolve_relative_path_rejects_absolute(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    with pytest.raises(ValueError):
        paths.resolve_relative_path(Path("/etc/passwd"))


def test_resolve_relative_path_rejects_traversal(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    with pytest.raises(ValueError):
        paths.resolve_relative_path(Path("..") / ".." / "outside")


def test_ensure_profile_layout_creates_dirs(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    assert paths.profile_dir(_PROFILE).is_dir()
    assert paths.runs_dir(_PROFILE).is_dir()


def test_ensure_run_layout_creates_run_dir(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    assert paths.run_dir(_PROFILE, _RUN).is_dir()


def test_layout_has_no_mutable_cookies_json(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    found = list(tmp_path.rglob("cookies.json"))
    assert found == []


def test_layout_has_no_mutable_latest_json(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    found = list(tmp_path.rglob("latest.json"))
    assert found == []


def test_cast_profile_traversal_creates_nothing_outside(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    before = sorted(p.name for p in tmp_path.parent.iterdir())
    with pytest.raises(Exception):
        paths.ensure_profile_layout(cast(ProfileId, "../../outside"))
    after = sorted(p.name for p in tmp_path.parent.iterdir())
    assert before == after
    assert not (tmp_path.parent / "outside").exists()


def test_cast_run_traversal_creates_nothing_outside(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    before = sorted(p.name for p in tmp_path.parent.iterdir())
    with pytest.raises(Exception):
        paths.ensure_run_layout(_PROFILE, cast(RunId, "../bad"))
    after = sorted(p.name for p in tmp_path.parent.iterdir())
    assert before == after
    assert not (paths.runs_dir(_PROFILE).parent.parent / "bad").exists()


def test_directory_permissions_best_effort(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions not enforced on this platform")
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    mode = paths.profile_dir(_PROFILE).stat().st_mode & 0o777
    assert mode == 0o700
