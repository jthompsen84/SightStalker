"""
sightstalker.sessions.manager — profile/session/run/context lifecycle.

``SessionManager`` connects the accepted contract models to the accepted
``BrowserEngine`` protocol. It coordinates exactly one run against one
session/profile, enforces one-profile-one-active-run via a file lock, and writes
immutable per-run storage-state snapshots.

This layer adds no SQL persistence, CLI, diagnostics orchestration, interaction
simulation, proxy/fingerprint registries, persistent browser ``user_data_dir``
contexts, or web/API surfaces. It depends only on the generic ``BrowserEngine``
protocol — never on Camoufox or Playwright.

Blocking filesystem/lock/state-store work is dispatched through
``asyncio.to_thread`` so it does not block the event loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from sightstalker.engines import BrowserContextHandle, BrowserEngine, BrowserRuntime
from sightstalker.models import (
    ArtifactRef,
    BrowserContextRecord,
    BrowserLaunchConfig,
    BrowserState,
    JsonObject,
    ProfileRecord,
    RunRecord,
    RunRequest,
    RunStatus,
    SessionRecord,
    ToolkitModel,
    utc_now,
)
from sightstalker.security.redaction import redact_exception
from sightstalker.sessions.locks import ProfileLockHandle, ProfileLockManager
from sightstalker.sessions.ids import (
    new_context_id,
    new_run_id,
    validate_profile_id,
    validate_session_id,
)
from sightstalker.sessions.paths import SessionPaths
from sightstalker.sessions.state_store import BrowserStateStore

# Reserved internal metadata keys.
_TIMEOUT_KEY = "_sightstalker_request_timeout_ms"
_CLEANUP_ERRORS_KEY = "_sightstalker_cleanup_errors"


class SessionLifecycleResult(ToolkitModel):
    """Immutable outcome of one managed session lifecycle."""

    run_record: RunRecord
    context_record: BrowserContextRecord | None
    updated_session: SessionRecord
    initial_state_ref: ArtifactRef | None = None
    final_state_ref: ArtifactRef | None = None
    relative_run_dir: Path


class SessionManager:
    """Creates managed session contexts over a generic ``BrowserEngine``."""

    def __init__(
        self,
        *,
        data_dir: Path,
        engine: BrowserEngine,
        lock_timeout_seconds: float = 0.0,
        paths: SessionPaths | None = None,
        state_store: BrowserStateStore | None = None,
        lock_manager: ProfileLockManager | None = None,
    ) -> None:
        self._paths = paths if paths is not None else SessionPaths(Path(data_dir))
        self._engine = engine
        self._state_store = (
            state_store if state_store is not None else BrowserStateStore(self._paths)
        )
        self._lock_manager = (
            lock_manager
            if lock_manager is not None
            else ProfileLockManager(self._paths, timeout_seconds=lock_timeout_seconds)
        )

    def open_context(
        self,
        *,
        session: SessionRecord,
        profile: ProfileRecord,
        request: RunRequest,
    ) -> ManagedSessionContext:
        """Return an async context manager orchestrating one run."""
        return ManagedSessionContext(
            engine=self._engine,
            paths=self._paths,
            state_store=self._state_store,
            lock_manager=self._lock_manager,
            session=session,
            profile=profile,
            request=request,
        )


class ManagedSessionContext:
    """Async context manager for a single run against a session/profile."""

    def __init__(
        self,
        *,
        engine: BrowserEngine,
        paths: SessionPaths,
        state_store: BrowserStateStore,
        lock_manager: ProfileLockManager,
        session: SessionRecord,
        profile: ProfileRecord,
        request: RunRequest,
    ) -> None:
        self._engine = engine
        self._paths = paths
        self._state_store = state_store
        self._lock_manager = lock_manager
        self._session = session
        self._profile = profile
        self._request = request

        self._entered = False
        self._exited = False

        self._lock: ProfileLockHandle | None = None
        self._runtime: BrowserRuntime | None = None
        self._context: BrowserContextHandle | None = None

        self._run_id = new_run_id()
        self._context_id = new_context_id()
        self._started_at = utc_now()

        self._initial_ref: ArtifactRef | None = None
        self._final_ref: ArtifactRef | None = None

        self._run_record: RunRecord | None = None
        self._context_record: BrowserContextRecord | None = None
        self._result: SessionLifecycleResult | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def run_record(self) -> RunRecord:
        if self._run_record is None:
            raise RuntimeError("run_record is unavailable until __aenter__ completes")
        return self._run_record

    @property
    def context_record(self) -> BrowserContextRecord:
        if self._context_record is None:
            raise RuntimeError(
                "context_record is unavailable until __aenter__ completes"
            )
        return self._context_record

    @property
    def context(self) -> BrowserContextHandle:
        if self._context is None:
            raise RuntimeError("context is unavailable until __aenter__ completes")
        return self._context

    @property
    def result(self) -> SessionLifecycleResult | None:
        return self._result

    # ------------------------------------------------------------------
    # Enter
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        session = self._session
        profile = self._profile
        request = self._request
        cfg = session.config

        # 1-2. Noun consistency.
        if profile.profile_id != session.profile_id:
            raise ValueError("profile.profile_id does not match session.profile_id")
        if request.session_id != session.session_id:
            raise ValueError("request.session_id does not match session.session_id")

        # 3. Runtime-validate identifiers used as path components / keys.
        profile_id = validate_profile_id(profile.profile_id)
        validate_session_id(session.session_id)
        validate_session_id(request.session_id)

        # 4-5. Reject deferred launch features before any work.
        if cfg.launch.user_data_dir is not None:
            raise ValueError(
                "BrowserLaunchConfig.user_data_dir is not supported by "
                "SESSION-STATE-1; persistent browser profiles are deferred to a "
                "future persistent-profile PR"
            )
        if cfg.launch.fingerprint is not None:
            raise ValueError(
                "FingerprintConfig mapping is deferred to profile/fingerprint "
                "registry PRs"
            )

        # 6. SessionPaths is the lock/filesystem authority; verify profile_dir.
        expected_profile_dir = self._paths.profile_dir(profile_id)
        if Path(profile.profile_dir).resolve() != expected_profile_dir.resolve():
            raise ValueError(
                "profile.profile_dir does not match the SessionPaths authority"
            )

        run_id = self._run_id
        context_id = self._context_id

        try:
            # 9. Profile layout first (lock file needs a parent directory).
            await asyncio.to_thread(self._paths.ensure_profile_layout, profile_id)
            # 10. Acquire the profile lock before creating the run layout.
            self._lock = await asyncio.to_thread(
                self._lock_manager.acquire, profile
            )
            # 11. Run layout only after the lock is held.
            await asyncio.to_thread(
                self._paths.ensure_run_layout, profile_id, run_id
            )
            # 12. Lifecycle wall-clock start.
            self._started_at = utc_now()
            # 13. Resolve the initial browser state (fail closed on bad prior state).
            initial_state = await self._resolve_initial_state()
            # 14. Persist a run-local initial snapshot when enabled.
            if cfg.persist_storage_state and cfg.capture_initial_storage_state:
                self._initial_ref = await asyncio.to_thread(
                    self._state_store.write_initial_state,
                    profile_id=profile_id,
                    run_id=run_id,
                    session_id=session.session_id,
                    state=initial_state,
                )
            # 15. Per-run launch config (never mutate the session's config).
            launch_config = self._build_launch_config(request.headed_override)
            # 16. Launch the engine.
            self._runtime = await self._engine.launch(launch_config)
            # 17. Create the isolated context.
            context_initial = (
                initial_state if cfg.persist_storage_state else None
            )
            self._context = await self._runtime.new_context(
                cfg.context,
                initial_state=context_initial,
                context_id=context_id,
            )
            # 18-19. Records describing the in-flight run.
            self._run_record = RunRecord(
                run_id=run_id,
                session_id=session.session_id,
                status="running",
                started_at=self._started_at,
                start_url=request.start_url,
                metadata=self._build_metadata(),
                artifacts=self._collected_artifacts(),
            )
            self._context_record = BrowserContextRecord(
                context_id=context_id,
                run_id=run_id,
                session_id=session.session_id,
                initial_storage_state=self._initial_ref,
            )
        except BaseException:
            await self._enter_failure_cleanup()
            raise

        self._entered = True
        return self

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        try:
            if exc is not None:
                await self._handle_caller_exception(exc)
            else:
                await self._handle_success()
        finally:
            self._exited = True
        # Never suppress a caller exception.
        return False

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    async def _resolve_initial_state(self) -> BrowserState:
        cfg = self._session.config
        prior = self._session.latest_final_state
        if cfg.persist_storage_state and prior is not None:
            # Fail closed: read_state raises SessionStateError on any integrity
            # problem (missing/corrupt/hash/size/path-unsafe). The carried-forward
            # snapshot preserves its own engine_name.
            return await asyncio.to_thread(self._state_store.read_state, prior)
        return BrowserState(engine_name=cfg.launch.engine_name)

    def _build_launch_config(self, headed_override: bool | None) -> BrowserLaunchConfig:
        launch = self._session.config.launch
        if headed_override is None:
            return launch
        mode = "headed" if headed_override else "headless"
        return launch.model_copy(update={"mode": mode})

    def _build_metadata(self) -> JsonObject:
        metadata: JsonObject = dict(self._request.metadata)
        # Explicit RunRequest.timeout_ms wins over any pre-seeded value.
        metadata[_TIMEOUT_KEY] = self._request.timeout_ms
        return metadata

    def _collected_artifacts(self) -> tuple[ArtifactRef, ...]:
        refs: list[ArtifactRef] = []
        if self._initial_ref is not None:
            refs.append(self._initial_ref)
        if self._final_ref is not None:
            refs.append(self._final_ref)
        return tuple(refs)

    async def _handle_success(self) -> None:
        cleanup_errors: list[str] = []
        first_exc: BaseException | None = None

        capture_err = await self._capture_and_record_final_state()
        if capture_err is not None:
            cleanup_errors.append(redact_exception(capture_err))
            first_exc = first_exc or capture_err

        ctx_err = await self._close_context()
        if ctx_err is not None:
            cleanup_errors.append(redact_exception(ctx_err))
            first_exc = first_exc or ctx_err

        rt_err = await self._close_runtime()
        if rt_err is not None:
            cleanup_errors.append(redact_exception(rt_err))
            first_exc = first_exc or rt_err

        lock_err = self._release_lock()
        if lock_err is not None:
            cleanup_errors.append(redact_exception(lock_err))
            first_exc = first_exc or lock_err

        completed_at = utc_now()

        if first_exc is not None:
            # An otherwise-successful user block hit a cleanup failure. The lock
            # has already been released above. Build a failed record, set the
            # result, then re-raise the cleanup failure.
            self._run_record = self._build_terminal_record(
                status="failed",
                completed_at=completed_at,
                error=first_exc,
                cleanup_errors=cleanup_errors,
            )
            self._result = self._build_result(advance_final=False)
            raise first_exc

        self._run_record = self._build_terminal_record(
            status="succeeded",
            completed_at=completed_at,
            error=None,
            cleanup_errors=cleanup_errors,
        )
        self._result = self._build_result(advance_final=True)

    async def _handle_caller_exception(self, exc: BaseException) -> None:
        cleanup_errors: list[str] = []

        capture_err = await self._capture_and_record_final_state()
        if capture_err is not None:
            cleanup_errors.append(redact_exception(capture_err))

        ctx_err = await self._close_context()
        if ctx_err is not None:
            cleanup_errors.append(redact_exception(ctx_err))

        rt_err = await self._close_runtime()
        if rt_err is not None:
            cleanup_errors.append(redact_exception(rt_err))

        lock_err = self._release_lock()
        if lock_err is not None:
            cleanup_errors.append(redact_exception(lock_err))

        completed_at = utc_now()
        # The caller exception is authoritative for error_type/message; cleanup
        # failures are recorded only as redacted summaries in metadata.
        self._run_record = self._build_terminal_record(
            status="failed",
            completed_at=completed_at,
            error=exc,
            cleanup_errors=cleanup_errors,
        )
        # Failed runs never advance latest_final_state.
        self._result = self._build_result(advance_final=False)

    # ------------------------------------------------------------------
    # Best-effort cleanup primitives
    # ------------------------------------------------------------------

    async def _capture_and_record_final_state(self) -> BaseException | None:
        cfg = self._session.config
        if not (cfg.persist_storage_state and cfg.capture_final_storage_state):
            return None
        if self._context is None:
            return None
        try:
            state = await self._context.storage_state()
            ref = await asyncio.to_thread(
                self._state_store.write_final_state,
                profile_id=self._profile.profile_id,
                run_id=self._run_id,
                session_id=self._session.session_id,
                state=state,
            )
        except BaseException as err:
            return err
        self._final_ref = ref
        if self._context_record is not None:
            self._context_record = self._context_record.model_copy(
                update={"final_storage_state": ref}
            )
        return None

    async def _close_context(self) -> BaseException | None:
        if self._context is None:
            return None
        result: BaseException | None = None
        try:
            await self._context.close()
        except BaseException as err:
            result = err
        if self._context_record is not None and self._context_record.closed_at is None:
            self._context_record = self._context_record.model_copy(
                update={"closed_at": utc_now()}
            )
        return result

    async def _close_runtime(self) -> BaseException | None:
        if self._runtime is None:
            return None
        try:
            await self._runtime.close()
        except BaseException as err:
            return err
        return None

    def _release_lock(self) -> BaseException | None:
        lock = self._lock
        if lock is None:
            return None
        try:
            lock.release()
        except BaseException as err:
            return err
        finally:
            self._lock = None
        return None

    async def _enter_failure_cleanup(self) -> None:
        # Order: context close -> runtime close -> lock release. Never leave a
        # profile lock held; never log sensitive state.
        if self._context is not None:
            try:
                await self._context.close()
            except BaseException:
                pass
        if self._runtime is not None:
            try:
                await self._runtime.close()
            except BaseException:
                pass
        if self._lock is not None:
            try:
                self._lock.release()
            except BaseException:
                pass
            self._lock = None

    # ------------------------------------------------------------------
    # Record construction
    # ------------------------------------------------------------------

    def _build_terminal_record(
        self,
        *,
        status: RunStatus,
        completed_at: datetime,
        error: BaseException | None,
        cleanup_errors: list[str],
    ) -> RunRecord:
        metadata = self._build_metadata()
        if cleanup_errors:
            metadata[_CLEANUP_ERRORS_KEY] = list(cleanup_errors)
        error_type: str | None = None
        error_message_redacted: str | None = None
        if error is not None:
            error_type = error.__class__.__name__
            error_message_redacted = redact_exception(error)
        return RunRecord(
            run_id=self._run_id,
            session_id=self._session.session_id,
            status=status,
            started_at=self._started_at,
            completed_at=completed_at,
            start_url=self._request.start_url,
            error_type=error_type,
            error_message_redacted=error_message_redacted,
            artifacts=self._collected_artifacts(),
            metadata=metadata,
        )

    def _build_updated_session(self, *, advance_final: bool) -> SessionRecord:
        update: dict[str, Any] = {}
        if self._initial_ref is not None:
            update["latest_initial_state"] = self._initial_ref
        if advance_final and self._final_ref is not None:
            update["latest_final_state"] = self._final_ref
        if not update:
            return self._session
        return self._session.model_copy(update=update)

    def _relative_run_dir(self) -> Path:
        run_dir = self._paths.run_dir(self._profile.profile_id, self._run_id)
        return self._paths.relative_to_data_dir(run_dir)

    def _build_result(self, *, advance_final: bool) -> SessionLifecycleResult:
        assert self._run_record is not None
        updated_session = self._build_updated_session(advance_final=advance_final)
        return SessionLifecycleResult(
            run_record=self._run_record,
            context_record=self._context_record,
            updated_session=updated_session,
            initial_state_ref=self._initial_ref,
            final_state_ref=self._final_ref,
            relative_run_dir=self._relative_run_dir(),
        )
