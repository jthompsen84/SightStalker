"""Tests for sightstalker.sessions.locks (spec 21.4)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from sightstalker.models import ProfileId, ProfileRecord
from sightstalker.sessions.locks import (
    ProfileLockManager,
    ProfileLockUnavailable,
)
from sightstalker.sessions.paths import SessionPaths

_PROFILE = cast(ProfileId, "prof_alpha_default")


def _profile(paths: SessionPaths, profile_id: ProfileId = _PROFILE) -> ProfileRecord:
    return ProfileRecord(
        profile_id=profile_id,
        name="alpha",
        profile_dir=paths.profile_dir(profile_id),
    )





def test_acquire_succeeds_for_unlocked_profile(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    handle = manager.acquire(_profile(paths))
    try:
        assert handle.profile_id == _PROFILE
    finally:
        handle.release()


def test_handle_can_be_released(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    handle = manager.acquire(_profile(paths))
    handle.release()
    # A fresh acquire now succeeds, proving the lock was freed.
    handle2 = manager.acquire(_profile(paths))
    handle2.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    handle = manager.acquire(_profile(paths))
    handle.release()
    handle.release()  # must not raise


def test_context_manager_releases_on_normal_exit(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    with manager.acquire(_profile(paths)):
        pass
    manager.acquire(_profile(paths)).release()


def test_context_manager_releases_on_exception(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with manager.acquire(_profile(paths)):
            raise _Boom()
    # Lock was released by __exit__ despite the exception.
    manager.acquire(_profile(paths)).release()


def test_second_acquire_fails_while_first_held(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    held = manager.acquire(_profile(paths))
    try:
        with pytest.raises(ProfileLockUnavailable):
            manager.acquire(_profile(paths))
    finally:
        held.release()


def test_second_acquire_uses_separate_call(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager_a = ProfileLockManager(paths)
    manager_b = ProfileLockManager(paths)
    held = manager_a.acquire(_profile(paths))
    try:
        with pytest.raises(ProfileLockUnavailable):
            manager_b.acquire(_profile(paths))
    finally:
        held.release()


def test_second_acquire_succeeds_after_release(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    first = manager.acquire(_profile(paths))
    first.release()
    second = manager.acquire(_profile(paths))
    second.release()


def test_lock_file_under_profile_directory(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    handle = manager.acquire(_profile(paths))
    try:
        assert handle.lock_path.parent == paths.profile_dir(_PROFILE)
    finally:
        handle.release()


def test_default_timeout_is_fail_fast(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    held = manager.acquire(_profile(paths))
    try:
        # No measurable blocking: default timeout is 0.0 → immediate raise.
        with pytest.raises(ProfileLockUnavailable):
            manager.acquire(_profile(paths))
    finally:
        held.release()


def test_unavailable_has_no_sensitive_state(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    held = manager.acquire(_profile(paths))
    try:
        with pytest.raises(ProfileLockUnavailable) as exc_info:
            manager.acquire(_profile(paths))
    finally:
        held.release()
    msg = str(exc_info.value)
    for token in ("cookie", "Cookie", "token", "password", "secret"):
        assert token not in msg


def test_unavailable_omits_absolute_lock_path(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    held = manager.acquire(_profile(paths))
    try:
        with pytest.raises(ProfileLockUnavailable) as exc_info:
            manager.acquire(_profile(paths))
    finally:
        held.release()
    msg = str(exc_info.value)
    assert str(tmp_path) not in msg
    assert str(paths.profile_lock_path(_PROFILE)) not in msg
    assert ".lock" not in msg
    # Cause chain must be dropped so the Timeout's path is not exposed.
    assert exc_info.value.__cause__ is None


def test_acquire_rejects_profile_dir_mismatch(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    bogus = ProfileRecord(
        profile_id=_PROFILE,
        name="alpha",
        profile_dir=tmp_path / "somewhere_else",
    )
    with pytest.raises(ValueError):
        manager.acquire(bogus)


def test_acquire_derives_lock_from_session_paths(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    manager = ProfileLockManager(paths)
    handle = manager.acquire(_profile(paths))
    try:
        # The lock path must come from SessionPaths, not profile.profile_dir.
        assert handle.lock_path == paths.profile_lock_path(_PROFILE)
    finally:
        handle.release()
