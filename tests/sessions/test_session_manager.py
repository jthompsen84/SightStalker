"""Tests for sightstalker.sessions.manager (spec 21.6).

Uses fake protocol-compliant engine classes; Camoufox is never imported.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from sightstalker.models import (
    ArtifactRef,
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
    ContextId,
    FingerprintConfig,
    ProfileId,
    ProfileRecord,
    RunRequest,
    SessionConfig,
    SessionId,
    SessionRecord,
)
from sightstalker.sessions.locks import ProfileLockManager, ProfileLockUnavailable
from sightstalker.sessions.manager import ManagedSessionContext, SessionManager
from sightstalker.sessions.paths import SessionPaths
from sightstalker.sessions.state_store import BrowserStateStore

_PROFILE = cast(ProfileId, "prof_alpha_default")
_PROFILE_B = cast(ProfileId, "prof_beta_default0")
_SESSION = cast(SessionId, "sess_alpha_default")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePageHandle:
    def __init__(self) -> None:
        self.goto_calls = 0

    @property
    def native_page(self) -> Any:
        return None

    async def goto(
        self, url: str, *, wait_until: str = "load", timeout_ms: int | None = None
    ) -> None:
        self.goto_calls += 1

    async def title(self) -> str:
        return "fake"

    async def url(self) -> str:
        return "about:blank"

    async def screenshot(
        self, *, path: str, full_page: bool = False, timeout_ms: int | None = None
    ) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeBrowserContext:
    def __init__(
        self,
        *,
        context_id: ContextId | None,
        initial_state: BrowserState | None,
        final_cookies: tuple[dict[str, Any], ...],
        storage_state_error: BaseException | None,
        close_error: BaseException | None,
    ) -> None:
        self._context_id = context_id or cast(ContextId, "ctx_fallback_00000000")
        self.received_initial_state = initial_state
        self._final_cookies = final_cookies
        self._storage_state_error = storage_state_error
        self._close_error = close_error
        self.closed = False
        self.new_page_calls = 0

    @property
    def context_id(self) -> ContextId:
        return self._context_id

    @property
    def native_context(self) -> Any:
        return None

    async def new_page(self) -> FakePageHandle:
        self.new_page_calls += 1
        return FakePageHandle()

    async def storage_state(self) -> BrowserState:
        if self._storage_state_error is not None:
            raise self._storage_state_error
        return BrowserState(engine_name="mock", cookies=self._final_cookies)

    async def start_tracing(self, *, name: str | None = None) -> None:
        return None

    async def stop_tracing(self, *, path: str) -> None:
        return None

    async def close(self) -> None:
        self.closed = True
        if self._close_error is not None:
            raise self._close_error


class FakeBrowserRuntime:
    def __init__(self, engine: "FakeBrowserEngine", config: BrowserLaunchConfig) -> None:
        self._engine = engine
        self.launch_config = config
        self.closed = False
        self.context: FakeBrowserContext | None = None
        self.new_context_calls = 0

    @property
    def engine_name(self) -> str:
        return "mock"

    @property
    def native_browser(self) -> Any:
        return None

    async def new_context(
        self,
        config: BrowserContextConfig,
        *,
        initial_state: BrowserState | None = None,
        context_id: ContextId | None = None,
    ) -> FakeBrowserContext:
        self.new_context_calls += 1
        if self._engine.new_context_error is not None:
            raise self._engine.new_context_error
        self.context = FakeBrowserContext(
            context_id=context_id,
            initial_state=initial_state,
            final_cookies=self._engine.final_cookies,
            storage_state_error=self._engine.storage_state_error,
            close_error=self._engine.context_close_error,
        )
        return self.context

    async def close(self) -> None:
        self.closed = True
        if self._engine.runtime_close_error is not None:
            raise self._engine.runtime_close_error


class FakeBrowserEngine:
    def __init__(
        self,
        *,
        launch_error: BaseException | None = None,
        new_context_error: BaseException | None = None,
        storage_state_error: BaseException | None = None,
        context_close_error: BaseException | None = None,
        runtime_close_error: BaseException | None = None,
        final_cookies: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.launch_error = launch_error
        self.new_context_error = new_context_error
        self.storage_state_error = storage_state_error
        self.context_close_error = context_close_error
        self.runtime_close_error = runtime_close_error
        self.final_cookies = final_cookies
        self.launch_calls = 0
        self.last_launch_config: BrowserLaunchConfig | None = None
        self.runtime: FakeBrowserRuntime | None = None
        self.closed = False

    @property
    def name(self) -> str:
        return "mock"

    async def launch(self, config: BrowserLaunchConfig) -> FakeBrowserRuntime:
        self.launch_calls += 1
        self.last_launch_config = config
        if self.launch_error is not None:
            raise self.launch_error
        self.runtime = FakeBrowserRuntime(self, config)
        return self.runtime

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _session_config(
    *,
    mode: str = "headless",
    user_data_dir: Path | None = None,
    fingerprint: FingerprintConfig | None = None,
    persist: bool = True,
    capture_initial: bool = True,
    capture_final: bool = True,
) -> SessionConfig:
    launch = BrowserLaunchConfig(
        engine_name="mock",
        mode=cast(Any, mode),
        user_data_dir=user_data_dir,
        fingerprint=fingerprint,
    )
    return SessionConfig(
        launch=launch,
        context=BrowserContextConfig(),
        persist_storage_state=persist,
        capture_initial_storage_state=capture_initial,
        capture_final_storage_state=capture_final,
    )


def _profile(paths: SessionPaths, profile_id: ProfileId = _PROFILE) -> ProfileRecord:
    return ProfileRecord(
        profile_id=profile_id,
        name="p",
        profile_dir=paths.profile_dir(profile_id),
    )


def _session(
    config: SessionConfig,
    *,
    profile_id: ProfileId = _PROFILE,
    session_id: SessionId = _SESSION,
    latest_final_state: ArtifactRef | None = None,
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        name="s",
        profile_id=profile_id,
        config=config,
        latest_final_state=latest_final_state,
    )


def _request(
    *,
    session_id: SessionId = _SESSION,
    start_url: str | None = None,
    headed_override: bool | None = None,
    metadata: dict[str, Any] | None = None,
    timeout_ms: int = 120_000,
) -> RunRequest:
    return RunRequest(
        session_id=session_id,
        start_url=start_url,
        headed_override=headed_override,
        metadata=metadata or {},
        timeout_ms=timeout_ms,
    )


def _manager(
    tmp_path: Path,
    engine: FakeBrowserEngine,
    *,
    paths: SessionPaths | None = None,
    lock_manager: ProfileLockManager | None = None,
) -> SessionManager:
    p = paths if paths is not None else SessionPaths(tmp_path)
    return SessionManager(
        data_dir=tmp_path,
        engine=cast(Any, engine),
        paths=p,
        state_store=BrowserStateStore(p),
        lock_manager=lock_manager
        if lock_manager is not None
        else ProfileLockManager(p, timeout_seconds=0.0),
    )


class _Boom(Exception):
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_manager_accepts_generic_engine(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, FakeBrowserEngine())
    assert isinstance(mgr, SessionManager)


async def test_open_context_returns_managed_context(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    assert isinstance(ctx, ManagedSessionContext)


async def test_rejects_profile_session_mismatch(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    session = _session(cfg)  # profile_id == _PROFILE
    bad_profile = _profile(p, _PROFILE_B)  # different id
    with pytest.raises(ValueError):
        async with mgr.open_context(
            session=session, profile=bad_profile, request=_request()
        ):
            pass


async def test_rejects_request_session_mismatch(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    bad_request = _request(session_id=cast(SessionId, "sess_other_default"))
    with pytest.raises(ValueError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=bad_request
        ):
            pass


async def test_access_before_enter_raises(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(RuntimeError):
        _ = ctx.context
    with pytest.raises(RuntimeError):
        _ = ctx.run_record
    with pytest.raises(RuntimeError):
        _ = ctx.context_record


async def test_enter_ensures_profile_layout(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ):
        assert p.profile_dir(_PROFILE).is_dir()
        assert p.runs_dir(_PROFILE).is_dir()


async def test_lock_acquired_before_run_layout(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    observations: dict[str, bool] = {}

    class _Spy(ProfileLockManager):
        def acquire(self, profile: ProfileRecord):  # type: ignore[override]
            # At acquire time, profile layout exists but no run dir does yet.
            runs = list(p.runs_dir(profile.profile_id).glob("run_*"))
            observations["run_dir_absent_at_acquire"] = runs == []
            observations["profile_layout_present"] = p.profile_dir(
                profile.profile_id
            ).is_dir()
            return super().acquire(profile)

    mgr = _manager(
        tmp_path,
        FakeBrowserEngine(),
        paths=p,
        lock_manager=_Spy(p, timeout_seconds=0.0),
    )
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        run_dir = p.run_dir(_PROFILE, ctx.run_record.run_id)
        assert run_dir.is_dir()
    assert observations["run_dir_absent_at_acquire"] is True
    assert observations["profile_layout_present"] is True


async def test_run_directory_created_after_lock(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        assert p.run_dir(_PROFILE, ctx.run_record.run_id).is_dir()


async def test_initial_state_file_created_when_enabled(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        initial = p.storage_state_initial_path(_PROFILE, ctx.run_record.run_id)
        assert initial.is_file()


async def test_previous_final_used_as_initial(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    store = BrowserStateStore(p)
    prior_run = cast(Any, "run_prior_0123456789abcdef")
    p.ensure_profile_layout(_PROFILE)
    p.ensure_run_layout(_PROFILE, prior_run)
    prior_ref = store.write_final_state(
        profile_id=_PROFILE,
        run_id=prior_run,
        session_id=_SESSION,
        state=BrowserState(engine_name="mock", cookies=({"name": "prev"},)),
    )
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    session = _session(cfg, latest_final_state=prior_ref)
    async with mgr.open_context(
        session=session, profile=_profile(p), request=_request()
    ):
        assert engine.runtime is not None
        ctx_obj = engine.runtime.context
        assert ctx_obj is not None
        assert ctx_obj.received_initial_state is not None
        assert ctx_obj.received_initial_state.cookies == ({"name": "prev"},)


async def test_corrupt_previous_final_fails_closed(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    store = BrowserStateStore(p)
    prior_run = cast(Any, "run_prior_0123456789abcdef")
    p.ensure_profile_layout(_PROFILE)
    p.ensure_run_layout(_PROFILE, prior_run)
    prior_ref = store.write_final_state(
        profile_id=_PROFILE,
        run_id=prior_run,
        session_id=_SESSION,
        state=BrowserState(engine_name="mock"),
    )
    bad_ref = prior_ref.model_copy(update={"sha256": "b" * 64})
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    session = _session(cfg, latest_final_state=bad_ref)
    from sightstalker.sessions.errors import SessionStateError

    with pytest.raises(SessionStateError):
        async with mgr.open_context(
            session=session, profile=_profile(p), request=_request()
        ):
            pass
    # Fail closed: engine never launched, lock released (re-acquire succeeds).
    assert engine.launch_calls == 0
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_initial_state_passed_to_new_context(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ):
        assert engine.runtime is not None
        ctx_obj = engine.runtime.context
        assert ctx_obj is not None
        assert ctx_obj.received_initial_state is not None
        assert ctx_obj.received_initial_state.engine_name == "mock"


async def test_enter_generates_valid_run_id(tmp_path: Path) -> None:
    from sightstalker.sessions.ids import validate_run_id

    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        assert validate_run_id(ctx.run_record.run_id) == ctx.run_record.run_id


async def test_enter_generates_valid_context_id(tmp_path: Path) -> None:
    from sightstalker.sessions.ids import validate_context_id

    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        cid = ctx.context_record.context_id
        assert validate_context_id(cid) == cid


async def test_run_status_running_inside_context(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        assert ctx.run_record.status == "running"


async def test_started_at_populated_inside_context(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ) as ctx:
        assert ctx.run_record.started_at is not None


async def test_start_url_copied(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg),
        profile=_profile(p),
        request=_request(start_url="https://example.com"),
    ) as ctx:
        assert ctx.run_record.start_url == "https://example.com"


async def test_metadata_includes_request_metadata(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg),
        profile=_profile(p),
        request=_request(metadata={"team": "qa"}),
    ) as ctx:
        assert ctx.run_record.metadata["team"] == "qa"


async def test_metadata_records_timeout_key(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg),
        profile=_profile(p),
        request=_request(timeout_ms=5000),
    ) as ctx:
        assert ctx.run_record.metadata["_sightstalker_request_timeout_ms"] == 5000


async def test_headed_override_true_launches_headed(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config(mode="headless")
    async with mgr.open_context(
        session=_session(cfg),
        profile=_profile(p),
        request=_request(headed_override=True),
    ):
        assert engine.last_launch_config is not None
        assert engine.last_launch_config.mode == "headed"


async def test_headed_override_false_launches_headless(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config(mode="headed")
    async with mgr.open_context(
        session=_session(cfg),
        profile=_profile(p),
        request=_request(headed_override=False),
    ):
        assert engine.last_launch_config is not None
        assert engine.last_launch_config.mode == "headless"


async def test_headed_override_does_not_mutate_session(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config(mode="headless")
    session = _session(cfg)
    async with mgr.open_context(
        session=session,
        profile=_profile(p),
        request=_request(headed_override=True),
    ):
        pass
    assert session.config.launch.mode == "headless"


async def test_manager_does_not_navigate(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg),
        profile=_profile(p),
        request=_request(start_url="https://example.com"),
    ):
        assert engine.runtime is not None
        assert engine.runtime.context is not None
        # Manager must not open pages or navigate on the caller's behalf.
        assert engine.runtime.context.new_page_calls == 0


async def test_exit_captures_final_state(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    assert ctx.result is not None
    assert ctx.result.final_state_ref is not None


async def test_exit_writes_final_file(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    rid = ""
    async with ctx:
        rid = ctx.run_record.run_id
    assert p.storage_state_final_path(_PROFILE, rid).is_file()


async def test_exit_closes_context(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ):
        pass
    assert engine.runtime is not None and engine.runtime.context is not None
    assert engine.runtime.context.closed is True


async def test_exit_closes_runtime(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ):
        pass
    assert engine.runtime is not None
    assert engine.runtime.closed is True


async def test_exit_releases_lock(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ):
        pass
    # Lock freed → re-acquire succeeds.
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_exit_sets_result(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    assert ctx.result is not None


async def test_success_status_succeeded(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    assert ctx.result is not None
    assert ctx.result.run_record.status == "succeeded"


async def test_success_completed_after_started(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    rec = ctx.result.run_record  # type: ignore[union-attr]
    assert rec.completed_at is not None and rec.started_at is not None
    assert rec.completed_at >= rec.started_at


async def test_success_updates_latest_final(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    assert ctx.result is not None
    assert ctx.result.updated_session.latest_final_state is not None


async def test_success_updates_latest_initial(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    assert ctx.result is not None
    assert ctx.result.updated_session.latest_initial_state is not None


async def test_success_artifacts_order(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    artifacts = ctx.result.run_record.artifacts  # type: ignore[union-attr]
    assert len(artifacts) == 2
    assert artifacts[0].artifact_type == "storage_state_initial"
    assert artifacts[1].artifact_type == "storage_state_final"


async def test_caller_exception_not_swallowed(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    with pytest.raises(_Boom):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            raise _Boom()


async def test_caller_exception_produces_failed_result(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):
        async with ctx:
            raise _Boom()
    assert ctx.result is not None
    assert ctx.result.run_record.status == "failed"


async def test_failed_result_uses_redacted_message(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):
        async with ctx:
            raise _Boom("boom happened")
    assert ctx.result is not None
    assert ctx.result.run_record.error_message_redacted is not None


async def test_failed_completed_after_started(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):
        async with ctx:
            raise _Boom()
    rec = ctx.result.run_record  # type: ignore[union-attr]
    assert rec.completed_at is not None and rec.started_at is not None
    assert rec.completed_at >= rec.started_at


async def test_failed_does_not_advance_latest_final(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):
        async with ctx:
            raise _Boom()
    assert ctx.result is not None
    assert ctx.result.updated_session.latest_final_state is None


async def test_failed_captured_final_in_artifacts(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(final_cookies=({"name": "c"},))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):
        async with ctx:
            raise _Boom()
    rec = ctx.result.run_record  # type: ignore[union-attr]
    types = {a.artifact_type for a in rec.artifacts}
    assert "storage_state_final" in types
    result = ctx.result
    assert result is not None
    assert result.context_record is not None
    assert result.context_record.final_storage_state is not None


async def test_lock_released_after_caller_exception(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    with pytest.raises(_Boom):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            raise _Boom()
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_runtime_closed_after_caller_exception(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    with pytest.raises(_Boom):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            raise _Boom()
    assert engine.runtime is not None and engine.runtime.closed is True


async def test_context_closed_after_caller_exception(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    with pytest.raises(_Boom):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            raise _Boom()
    assert engine.runtime is not None and engine.runtime.context is not None
    assert engine.runtime.context.closed is True


async def test_cleanup_failure_does_not_mask_caller_exception(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(context_close_error=RuntimeError("close fail"))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):  # original exception, not the cleanup error
        async with ctx:
            raise _Boom()
    # Cleanup error is recorded as a redacted summary, lock still released.
    rec = ctx.result.run_record  # type: ignore[union-attr]
    assert rec.error_type == "_Boom"
    assert "_sightstalker_cleanup_errors" in rec.metadata
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_final_capture_failure_on_success_raises(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(storage_state_error=RuntimeError("snap fail"))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    with pytest.raises(RuntimeError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            pass
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_context_close_failure_on_success_raises(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(context_close_error=RuntimeError("ctx close fail"))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    with pytest.raises(RuntimeError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            pass
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_runtime_close_failure_on_success_raises(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(runtime_close_error=RuntimeError("rt close fail"))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    with pytest.raises(RuntimeError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            pass
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_persist_false_writes_no_files(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config(persist=False)
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    rid = ""
    async with ctx:
        rid = ctx.run_record.run_id
    assert not p.storage_state_initial_path(_PROFILE, rid).exists()
    assert not p.storage_state_final_path(_PROFILE, rid).exists()
    assert ctx.result is not None
    assert ctx.result.run_record.artifacts == ()


async def test_capture_initial_false_no_initial_file(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config(capture_initial=False)
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    rid = ""
    async with ctx:
        rid = ctx.run_record.run_id
    assert not p.storage_state_initial_path(_PROFILE, rid).exists()


async def test_capture_final_false_no_final_file(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config(capture_final=False)
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    rid = ""
    async with ctx:
        rid = ctx.run_record.run_id
    assert not p.storage_state_final_path(_PROFILE, rid).exists()


async def test_user_data_dir_rejected_before_launch(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config(user_data_dir=tmp_path / "ud")
    with pytest.raises(ValueError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            pass
    assert engine.launch_calls == 0


async def test_fingerprint_rejected_before_launch(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config(fingerprint=FingerprintConfig(locale="en-US"))
    with pytest.raises(ValueError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            pass
    assert engine.launch_calls == 0


async def test_concurrent_same_profile_fails(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    async with mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    ):
        with pytest.raises(ProfileLockUnavailable):
            async with mgr.open_context(
                session=_session(cfg), profile=_profile(p), request=_request()
            ):
                pass


async def test_different_profiles_run_concurrently(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg_a = _session_config()
    cfg_b = _session_config()
    session_b = _session(
        cfg_b,
        profile_id=_PROFILE_B,
        session_id=cast(SessionId, "sess_beta_default0"),
    )
    request_b = _request(session_id=cast(SessionId, "sess_beta_default0"))
    async with mgr.open_context(
        session=_session(cfg_a), profile=_profile(p), request=_request()
    ):
        async with mgr.open_context(
            session=session_b, profile=_profile(p, _PROFILE_B), request=request_b
        ):
            pass


async def test_artifact_relative_paths_are_relative(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    for a in ctx.result.run_record.artifacts:  # type: ignore[union-attr]
        assert not a.relative_path.is_absolute()


async def test_no_raw_cookies_in_error_message(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(final_cookies=({"name": "s", "value": "COOKIEVAL999"},))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    with pytest.raises(_Boom):
        async with ctx:
            raise _Boom("failure")
    rec = ctx.result.run_record  # type: ignore[union-attr]
    assert "COOKIEVAL999" not in (rec.error_message_redacted or "")
    for value in rec.metadata.get("_sightstalker_cleanup_errors", []):
        assert "COOKIEVAL999" not in value


async def test_enter_failure_after_lock_releases_lock(tmp_path: Path) -> None:
    # Failure injected after lock acquisition (bad prior final state).
    p = SessionPaths(tmp_path)
    store = BrowserStateStore(p)
    prior_run = cast(Any, "run_prior_0123456789abcdef")
    p.ensure_profile_layout(_PROFILE)
    p.ensure_run_layout(_PROFILE, prior_run)
    prior_ref = store.write_final_state(
        profile_id=_PROFILE,
        run_id=prior_run,
        session_id=_SESSION,
        state=BrowserState(engine_name="mock"),
    )
    bad_ref = prior_ref.model_copy(update={"size_bytes": prior_ref.size_bytes + 5})
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    from sightstalker.sessions.errors import SessionStateError

    with pytest.raises(SessionStateError):
        async with mgr.open_context(
            session=_session(cfg, latest_final_state=bad_ref),
            profile=_profile(p),
            request=_request(),
        ):
            pass
    assert engine.launch_calls == 0
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_enter_failure_after_launch_closes_runtime(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine(new_context_error=RuntimeError("ctx create fail"))
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    with pytest.raises(RuntimeError):
        async with mgr.open_context(
            session=_session(cfg), profile=_profile(p), request=_request()
        ):
            pass
    assert engine.runtime is not None and engine.runtime.closed is True
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_enter_failure_after_context_closes_context_and_runtime(
    tmp_path: Path,
) -> None:
    p = SessionPaths(tmp_path)
    engine = FakeBrowserEngine()
    mgr = _manager(tmp_path, engine, paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )

    # Force a failure in __aenter__ strictly after the context is created.
    def _boom() -> tuple[ArtifactRef, ...]:
        raise _Boom("after context")

    setattr(ctx, "_collected_artifacts", _boom)

    with pytest.raises(_Boom):
        async with ctx:
            pass
    assert engine.runtime is not None
    assert engine.runtime.context is not None
    assert engine.runtime.context.closed is True
    assert engine.runtime.closed is True
    ProfileLockManager(p).acquire(_profile(p)).release()


async def test_context_record_non_none_when_context_created(tmp_path: Path) -> None:
    p = SessionPaths(tmp_path)
    mgr = _manager(tmp_path, FakeBrowserEngine(), paths=p)
    cfg = _session_config()
    ctx = mgr.open_context(
        session=_session(cfg), profile=_profile(p), request=_request()
    )
    async with ctx:
        pass
    assert ctx.result is not None
    assert ctx.result.context_record is not None
