"""
sightstalker.sessions.locks — one-profile-one-active-run file locking.

A profile may be used by at most one active run at a time. The lock is backed
by ``filelock`` so it is visible across processes, not just within one Python
process. Each ``acquire`` builds a *distinct* underlying lock object (no
per-profile caching), so a second acquire while the first is held fails fast.

``ProfileLockUnavailable`` messages intentionally expose only the profile id and
a stable reason; they never include absolute paths, wrapped raw exception
strings, or any browser/runtime payload.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Self

from filelock import BaseFileLock, FileLock, Timeout

from sightstalker.models import ProfileId, ProfileRecord
from sightstalker.sessions.ids import validate_profile_id
from sightstalker.sessions.paths import SessionPaths


class ProfileLockUnavailable(RuntimeError):
    """Raised when a profile lock cannot be acquired (already held elsewhere)."""


class ProfileLockHandle:
    """Handle for an acquired profile lock; release is idempotent."""

    profile_id: ProfileId
    lock_path: Path

    def __init__(
        self,
        *,
        profile_id: ProfileId,
        lock_path: Path,
        lock: BaseFileLock,
    ) -> None:
        self.profile_id = profile_id
        self.lock_path = lock_path
        self._lock = lock
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            self._lock.release()
        except Exception:
            # Release is best-effort and idempotent; never surface raw paths.
            pass

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


class ProfileLockManager:
    """Acquires profile-scoped locks derived solely from ``SessionPaths``."""

    def __init__(self, paths: SessionPaths, *, timeout_seconds: float = 0.0) -> None:
        self._paths = paths
        self._timeout_seconds = timeout_seconds

    def acquire(self, profile: ProfileRecord) -> ProfileLockHandle:
        """
        Acquire the lock for ``profile``.

        The lock path is derived from ``profile.profile_id`` through
        ``SessionPaths``. ``profile.profile_dir`` is validated against the
        ``SessionPaths`` authority and is never trusted as a lock root or passed
        to the browser engine.
        """
        profile_id = validate_profile_id(profile.profile_id)
        expected_dir = self._paths.profile_dir(profile_id)
        if Path(profile.profile_dir).resolve() != expected_dir.resolve():
            raise ValueError(
                "profile.profile_dir does not match the SessionPaths authority"
            )
        return self.acquire_by_id(profile_id)

    def acquire_by_id(self, profile_id: ProfileId) -> ProfileLockHandle:
        validated = validate_profile_id(profile_id)
        lock_path = self._paths.profile_lock_path(validated)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Distinct underlying lock object per acquire; no singleton reuse.
        # thread_local=False is required: SessionManager acquires the lock in a
        # worker thread (asyncio.to_thread) but releases it on the main thread.
        # With filelock's default thread-local state the lock would never be
        # released from a different thread, leaking the profile lock.
        lock = FileLock(str(lock_path), is_singleton=False, thread_local=False)
        try:
            lock.acquire(timeout=self._timeout_seconds)
        except Timeout:
            # Do not chain the raw Timeout (it embeds the absolute lock path).
            raise ProfileLockUnavailable(
                f"profile lock unavailable for {validated}"
            ) from None

        return ProfileLockHandle(
            profile_id=validated,
            lock_path=lock_path,
            lock=lock,
        )
