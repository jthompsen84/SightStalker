"""
sightstalker.ops.runs — shared managed-run orchestration.

Owns the behavior-preserving managed-run executor moved out of ``cli.runs``:
load session/profile, validate runtime config before any lock/launch, apply a
frozen-model headed/headless override, open exactly one managed context, run a
single trusted plan, then persist run/context/artifact metadata in one
transaction. Raw navigation URLs and ``data:`` bodies are never persisted or
printed — only the redacted metadata URL is. Artifact files are never deleted if
metadata persistence fails; an orphan warning is emitted instead.

This module is presentation-neutral: it imports no CLI command/rendering module,
no Typer/Rich, and no concrete browser adapter. Failures are raised as sanitized
resilience errors that preserve the accepted public error labels.
"""

from __future__ import annotations

from asyncio import CancelledError
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from sightstalker.artifacts import ArtifactManager, ArtifactPaths
from sightstalker.diagnostics import DiagnosticArtifactRecorder, DiagnosticTarget
from sightstalker.models import ProfileRecord, RunRequest, SessionId, SessionRecord
from sightstalker.ops.dependencies import EngineFactory
from sightstalker.ops.errors import OpsPersistenceFailure
from sightstalker.ops.plans import JsonObject, JsonValue, Plan, PlanResult
from sightstalker.ops.surface import RunSurface
from sightstalker.environment.models import (
    ContextConfigResolution,
    LaunchConfigOverrides,
    RunConfigOverrides,
)
from sightstalker.environment.protocols import ContextConfigResolver
from sightstalker.ops.initializers import (
    ContextInitializationScope,
    ContextInitializer,
    ContextInitializerChain,
)
from sightstalker.persistence import (
    ArtifactRepository,
    AsyncSessionFactory,
    BrowserContextRepository,
    ProfileRepository,
    RunRepository,
    SessionRepository,
    database_session,
)
from sightstalker.persistence.serialization import persistable_session_config
from sightstalker.resilience.errors import (
    BrowserRuntimeError,
    SecurityRefusal,
    SightStalkerError,
    UsageError,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_operator_message,
    sanitize_title_for_operator as sanitize_title_for_output,
    sanitize_url_for_operator_metadata as sanitize_url_for_metadata,
)
from sightstalker.sessions import ManagedSessionContext, SessionManager

# Run-order policy (ops owns deterministic allocation).
_RUN_ORDER_INITIAL = 0
_RUN_ORDER_FINAL = 100

_ORPHAN_WARNING = (
    "artifact files were written but metadata persistence failed; "
    "the files were left in place and not deleted"
)


def _empty_warnings() -> tuple[str, ...]:
    return ()


@dataclass(frozen=True)
class ManagedRunResult:
    """Behavior-neutral container for managed-run output and warnings."""

    data: JsonObject
    warnings: tuple[str, ...] = field(default_factory=_empty_warnings)


def _normalize_mode_overrides(
    headed_override: bool | None,
    run_config_overrides: RunConfigOverrides | None,
) -> RunConfigOverrides | None:
    """Fold ``headed_override`` into run-tier ``launch.mode`` for the resolver.

    If both ``headed_override`` and an explicit ``launch.mode`` override are
    supplied and disagree, raise ``UsageError`` before any launch. If they agree
    (or only one is supplied), return overrides carrying the single effective
    mode at the run-override tier.
    """
    if headed_override is None:
        return run_config_overrides

    headed_mode = "headed" if headed_override else "headless"
    existing_launch = (
        run_config_overrides.launch if run_config_overrides is not None else None
    )
    existing_mode = existing_launch.mode if existing_launch is not None else None

    if existing_mode is not None and existing_mode != headed_mode:
        raise UsageError(
            "conflicting launch mode: headed_override disagrees with "
            "run override launch.mode"
        )

    base = run_config_overrides if run_config_overrides is not None else (
        RunConfigOverrides()
    )
    launch_override = (
        existing_launch.model_copy(update={"mode": headed_mode})
        if existing_launch is not None
        else LaunchConfigOverrides(mode=headed_mode)
    )
    return base.model_copy(update={"launch": launch_override})


def _apply_mode_override(
    session: SessionRecord, headed_override: bool | None
) -> SessionRecord:
    if headed_override is None:
        return session
    mode = "headed" if headed_override else "headless"
    new_launch = session.config.launch.model_copy(update={"mode": mode})
    new_config = session.config.model_copy(update={"launch": new_launch})
    return session.model_copy(update={"config": new_config})


def _build_request(
    session_id: SessionId, metadata_url_redacted: str, timeout_ms: int | None
) -> RunRequest:
    kwargs: dict[str, object] = {
        "session_id": session_id,
        "start_url": metadata_url_redacted,
    }
    if timeout_ms is not None:
        kwargs["timeout_ms"] = timeout_ms
    try:
        return RunRequest(**kwargs)  # type: ignore[arg-type]
    except Exception:
        raise UsageError("invalid --timeout-ms value") from None


def _is_json_safe(value: object) -> bool:
    """Return True if ``value`` is a JSON-safe scalar/list/dict tree."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)  # type: ignore[misc]
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_safe(item)  # type: ignore[misc]
            for key, item in value.items()  # type: ignore[misc]
        )
    return False


def _sanitize_extra_value(value: JsonValue) -> JsonValue:
    """Recursively sanitize a JSON-safe value for operator output."""
    if isinstance(value, str):
        return sanitize_operator_message(value)
    if isinstance(value, list):
        return [_sanitize_extra_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_extra_value(item) for key, item in value.items()}
    return value


def _safe_extra(extra: JsonObject) -> JsonObject:
    """Validate and operator-sanitize ``PlanResult.extra`` before output merge.

    Rejects non-JSON-safe values with a classified failure (never leaking the
    unsafe value), then recursively redacts token-like / URL-credential strings
    so no raw secret or ``data:`` body reaches public output.
    """
    if not _is_json_safe(extra):
        raise BrowserRuntimeError("plan produced non-JSON-safe output metadata")
    sanitized: JsonObject = {}
    for key, value in extra.items():
        sanitized[key] = _sanitize_extra_value(value)
    return sanitized


async def _persist_run(
    *,
    factory: AsyncSessionFactory,
    session_id: SessionId,
    managed: ManagedSessionContext,
    plan_result: PlanResult,
) -> None:
    result = managed.result
    if result is None:  # pragma: no cover - defensive
        raise OpsPersistenceFailure("run produced no lifecycle result")
    run_record = result.run_record
    context_record = result.context_record
    initial_ref = result.initial_state_ref
    final_ref = result.final_state_ref
    run_id = run_record.run_id

    try:
        async with database_session(factory) as session:
            async with session.begin():
                runs = RunRepository(session)
                artifacts = ArtifactRepository(session)
                contexts = BrowserContextRepository(session)
                sessions = SessionRepository(session)

                await runs.create(run_record)
                if initial_ref is not None:
                    await artifacts.create(
                        initial_ref,
                        session_id=session_id,
                        run_id=run_id,
                        run_order=_RUN_ORDER_INITIAL,
                    )
                for ref, order in plan_result.diagnostics:
                    await artifacts.create(
                        ref,
                        session_id=session_id,
                        run_id=run_id,
                        run_order=order,
                    )
                if final_ref is not None:
                    await artifacts.create(
                        final_ref,
                        session_id=session_id,
                        run_id=run_id,
                        run_order=_RUN_ORDER_FINAL,
                    )
                if context_record is not None:
                    await contexts.create(context_record)
                await sessions.set_latest_artifacts(
                    session_id=session_id,
                    latest_initial=initial_ref,
                    latest_final=final_ref,
                )
    except SightStalkerError:
        raise
    except Exception as exc:  # noqa: BLE001 - orphan policy: keep files
        raise OpsPersistenceFailure(
            f"run metadata persistence failed: {type(exc).__name__}",
            warnings=(_ORPHAN_WARNING,),
        ) from None


def _build_context_initialization_scope(
    *,
    managed: ManagedSessionContext,
    profile: ProfileRecord,
    session: SessionRecord,
    request: RunRequest,
    resolution: ContextConfigResolution | None,
) -> ContextInitializationScope:
    """Build the scope handed to trusted initializers.

    Reuses the resolver's ``ContextConfigResolution`` when one was produced;
    otherwise synthesizes a minimal resolution from the exact effective session
    used to open the context (no re-resolution, no profile selection). This is
    only called when initializers are actually supplied.
    """
    effective_resolution = resolution
    if effective_resolution is None:
        effective_resolution = ContextConfigResolution(
            launch=session.config.launch,
            context=session.config.context,
            environment_profile_id=session.config.context.environment_profile_id,
            applied_environment_fields=(),
        )
    return ContextInitializationScope(
        context=managed.context,
        profile=profile,
        session=session,
        request=request,
        resolution=effective_resolution,
    )


async def execute_managed_run(
    *,
    data_dir: Path,
    session_factory: AsyncSessionFactory,
    engine_factory: EngineFactory,
    session_id: SessionId,
    raw_navigation_url: str,
    metadata_url_redacted: str,
    headed_override: bool | None,
    timeout_ms: int | None,
    plan: Plan,
    context_config_resolver: ContextConfigResolver | None = None,
    run_config_overrides: RunConfigOverrides | None = None,
    context_initializers: tuple[ContextInitializer, ...] = (),
) -> ManagedRunResult:
    """Run one managed, one-shot browser run and persist its metadata.

    When ``context_config_resolver`` is supplied, the resolver produces the
    effective launch/context config before engine launch and ``headed_override``
    is normalized into a run-tier ``launch.mode`` override. When no resolver is
    supplied, behavior is preserved exactly and ``_apply_mode_override`` performs
    the headed/headless override.
    """
    # 1-3. Load session + profile.
    async with database_session(session_factory) as session:
        sessions = SessionRepository(session)
        profiles = ProfileRepository(session, data_dir=data_dir)
        session_record = await sessions.require(session_id)
        profile_record = await profiles.require(session_record.profile_id)

    request = _build_request(session_id, metadata_url_redacted, timeout_ms)

    # Captured only when a resolver runs; reused for the initializer scope so we
    # never re-resolve. Stays None in the no-resolver branch (synthesized later
    # only if initializers are actually supplied).
    resolved_resolution: ContextConfigResolution | None = None

    if context_config_resolver is not None:
        # Resolver branch: normalize headed_override into a run override, resolve
        # effective config, then build an effective session record.
        effective_overrides = _normalize_mode_overrides(
            headed_override, run_config_overrides
        )
        resolution = await context_config_resolver.resolve(
            profile=profile_record,
            session=session_record,
            request=request,
            overrides=effective_overrides,
        )
        resolved_resolution = resolution
        new_config = session_record.config.model_copy(
            update={"launch": resolution.launch, "context": resolution.context}
        )
        session_record = session_record.model_copy(update={"config": new_config})
    else:
        # No-resolver branch: preserve current behavior exactly.
        if run_config_overrides is not None:
            raise UsageError(
                "run config overrides require a context config resolver"
            )
        session_record = _apply_mode_override(session_record, headed_override)

    # 4. Validate runtime config before any lock/browser/artifact work.
    try:
        persistable_session_config(session_record.config)
    except SightStalkerError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SecurityRefusal(
            f"session runtime config is not safe to run: {type(exc).__name__}"
        ) from None

    # 6. Lazily build the engine from the (effective) session engine name.
    engine = engine_factory(session_record.config.launch.engine_name)

    # 7. Manager + request (raw URL never persisted; metadata URL only).
    manager = SessionManager(data_dir=data_dir, engine=engine)

    recorder = DiagnosticArtifactRecorder(ArtifactManager(ArtifactPaths(data_dir)))

    managed = manager.open_context(
        session=session_record, profile=profile_record, request=request
    )

    # 8. Enter (launch + lock). Enter failures are browser/runtime failures.
    try:
        await managed.__aenter__()
    except SightStalkerError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BrowserRuntimeError(
            f"browser run could not start: {type(exc).__name__}"
        ) from None

    base_target = DiagnosticTarget(
        session_id=session_id,
        run_id=managed.run_record.run_id,
        context_id=managed.context_record.context_id,
    )
    surface = RunSurface(
        managed=managed,
        raw_navigation_url=raw_navigation_url,
        recorder=recorder,
        base_target=base_target,
    )

    run_error: BaseException | None = None
    failure_phase: str | None = None
    plan_result = PlanResult()
    try:
        if context_initializers:
            failure_phase = "initializer"
            scope = _build_context_initialization_scope(
                managed=managed,
                profile=profile_record,
                session=session_record,
                request=request,
                resolution=resolved_resolution,
            )
            await ContextInitializerChain(context_initializers).initialize(scope)

        failure_phase = "plan"
        plan_result = await plan(surface)
        failure_phase = None
    except BaseException as exc:  # capture to feed lifecycle exit
        run_error = exc
    finally:
        exc_type: type[BaseException] | None = (
            type(run_error) if run_error is not None else None
        )
        tb: TracebackType | None = (
            run_error.__traceback__ if run_error is not None else None
        )
        await managed.__aexit__(exc_type, run_error, tb)

    if run_error is not None:
        # Process-control exceptions are re-raised unchanged after cleanup.
        if isinstance(run_error, (KeyboardInterrupt, SystemExit, CancelledError)):
            raise run_error
        # Project errors are preserved as-is.
        if isinstance(run_error, SightStalkerError):
            raise run_error
        # Non-project errors are classified by the phase that failed.
        if failure_phase == "initializer":
            raise UsageError(
                f"context initializer failed: {type(run_error).__name__}"
            ) from None
        raise BrowserRuntimeError(
            f"run navigation/capture failed: {type(run_error).__name__}"
        ) from None

    # Validate/sanitize plan extra before merge into public output.
    safe_extra = _safe_extra(plan_result.extra)

    # 9. Persist metadata in one transaction (orphan policy on failure).
    await _persist_run(
        factory=session_factory,
        session_id=session_id,
        managed=managed,
        plan_result=plan_result,
    )

    result = managed.result
    assert result is not None
    data: JsonObject = {
        "run_id": result.run_record.run_id,
        "session_id": session_id,
        "status": result.run_record.status,
        "url": metadata_url_redacted,
        "final_url": sanitize_url_for_metadata(plan_result.final_url)
        if plan_result.final_url is not None
        else None,
        "title": sanitize_title_for_output(plan_result.title),
        "relative_run_dir": str(result.relative_run_dir),
        "artifacts": [
            {
                "artifact_id": ref.artifact_id,
                "artifact_type": ref.artifact_type,
                "relative_path": str(ref.relative_path),
            }
            for ref in result.run_record.artifacts
        ],
        "artifact_count": len(result.run_record.artifacts),
    }
    data.update(safe_extra)
    return ManagedRunResult(data=data, warnings=())


__all__ = [
    "ManagedRunResult",
    "execute_managed_run",
]
