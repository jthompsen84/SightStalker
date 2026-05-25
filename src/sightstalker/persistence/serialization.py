"""
sightstalker.persistence.serialization — Pydantic <-> DB-safe conversions.

Centralizes every conversion between accepted Pydantic contracts and DB row
values, and enforces the persistence security policy:

- canonical JSON (deterministic, no NaN/Infinity) for ``config_json`` /
  ``metadata_json`` Text columns;
- timezone-aware UTC timestamps in both directions;
- profile-dir containment + relative normalization against ``data_dir``;
- relative-path validation for artifact refs;
- live-model secret detection for session config (never trust ``model_dump``);
- redaction of arbitrary run metadata and health reasons.

This module imports only the Pydantic models and the shared redaction
utilities — never the artifact or session *managers*.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from sightstalker.models import (
    ArtifactId,
    ArtifactRef,
    ArtifactType,
    BrowserContextRecord,
    ContextId,
    HashAlgorithm,
    HealthStatus,
    JsonObject,
    ProfileId,
    ProfileRecord,
    RunId,
    RunRecord,
    RunStatus,
    SessionConfig,
    SessionHealthRecord,
    SessionId,
    SessionRecord,
)
from sightstalker.persistence.errors import (
    PersistenceIntegrityError,
    PersistenceSecurityError,
)
from sightstalker.security.redaction import (
    is_sensitive_header,
    is_sensitive_key,
    redact_mapping,
    redact_string,
)

# ---------------------------------------------------------------------------
# Runtime validators (static typing is insufficient at the DB boundary)
# ---------------------------------------------------------------------------

_PROFILE_ID: TypeAdapter[ProfileId] = TypeAdapter(ProfileId)
_SESSION_ID: TypeAdapter[SessionId] = TypeAdapter(SessionId)
_RUN_ID: TypeAdapter[RunId] = TypeAdapter(RunId)
_CONTEXT_ID: TypeAdapter[ContextId] = TypeAdapter(ContextId)
_ARTIFACT_ID: TypeAdapter[ArtifactId] = TypeAdapter(ArtifactId)
_ARTIFACT_TYPE: TypeAdapter[ArtifactType] = TypeAdapter(ArtifactType)
_RUN_STATUS: TypeAdapter[RunStatus] = TypeAdapter(RunStatus)
_HEALTH_STATUS: TypeAdapter[HealthStatus] = TypeAdapter(HealthStatus)
_HASH_ALGO: TypeAdapter[HashAlgorithm] = TypeAdapter(HashAlgorithm)
_ARTIFACT_REF: TypeAdapter[ArtifactRef] = TypeAdapter(ArtifactRef)


def _require(adapter: TypeAdapter[Any], value: object, what: str) -> Any:
    try:
        return adapter.validate_python(value)
    except Exception:
        raise PersistenceIntegrityError(f"{what} is malformed") from None


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------


def canonical_json(payload: object) -> str:
    """Encode ``payload`` as deterministic canonical JSON text.

    Sorted keys, compact separators, UTF-8 friendly, no NaN/Infinity. Raises
    ``PersistenceIntegrityError`` if the payload is not serializable.
    """
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise PersistenceIntegrityError("value is not JSON-serializable") from None


def decode_json_object(text: str) -> JsonObject:
    """Decode canonical JSON text and require a JSON object (mapping)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        raise PersistenceIntegrityError("stored JSON is invalid") from None
    if not isinstance(data, dict):
        raise PersistenceIntegrityError("stored JSON is not an object")
    return {str(k): v for k, v in data.items()}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Timestamp normalization
# ---------------------------------------------------------------------------


def to_utc(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def from_db_datetime(value: datetime | None) -> datetime | None:
    """Interpret a possibly-naive DB datetime as UTC and return tz-aware."""
    if value is None:
        return None
    return to_utc(value)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _assert_safe_relative(path: Path) -> str:
    """Validate that ``path`` is a safe relative path; return POSIX text."""
    raw = str(path)
    if "\x00" in raw:
        raise PersistenceIntegrityError("relative path contains a NUL byte")
    if path.is_absolute() or (path.drive != ""):
        raise PersistenceIntegrityError("artifact path must be relative")
    if raw == "" or raw == ".":
        raise PersistenceIntegrityError("artifact path must not be empty")
    parts = path.parts
    if not parts:
        raise PersistenceIntegrityError("artifact path must not be empty")
    for part in parts:
        if part == "..":
            raise PersistenceIntegrityError("artifact path must not contain traversal")
        if part in ("", "."):
            raise PersistenceIntegrityError("artifact path component is invalid")
    return PurePosixPath(*parts).as_posix()


def _profile_dir_to_relative(profile_dir: Path, *, data_dir: Path) -> str:
    """Normalize a profile dir to a relative POSIX path under ``data_dir``."""
    root = Path(data_dir).resolve()
    raw = str(profile_dir)
    if "\x00" in raw:
        raise PersistenceSecurityError("profile_dir contains a NUL byte")
    if profile_dir.is_absolute():
        resolved = profile_dir.resolve()
        if not resolved.is_relative_to(root):
            raise PersistenceSecurityError(
                "absolute profile_dir is outside the configured data directory"
            )
        rel = resolved.relative_to(root)
    else:
        if any(part == ".." for part in profile_dir.parts):
            raise PersistenceSecurityError("profile_dir must not contain traversal")
        rel = profile_dir
    text = PurePosixPath(*rel.parts).as_posix() if rel.parts else "."
    return text


def _profile_dir_from_relative(relative: str, *, data_dir: Path) -> Path:
    """Rehydrate an absolute contained profile dir under ``data_dir``."""
    root = Path(data_dir).resolve()
    if relative in ("", "."):
        return root
    return root / PurePosixPath(relative)


# ---------------------------------------------------------------------------
# ArtifactRef
# ---------------------------------------------------------------------------


def artifact_ref_to_row_values(
    ref: ArtifactRef,
    *,
    session_id: SessionId | None,
    run_id: RunId | None,
    run_order: int | None,
) -> dict[str, object]:
    """Validate an ``ArtifactRef`` and produce artifact row values."""
    validated = _require(_ARTIFACT_REF, ref.model_dump(mode="python"), "ArtifactRef")
    relative_text = _assert_safe_relative(validated.relative_path)
    return {
        "artifact_id": _require(_ARTIFACT_ID, validated.artifact_id, "ArtifactId"),
        "artifact_type": _require(
            _ARTIFACT_TYPE, validated.artifact_type, "ArtifactType"
        ),
        "relative_path": relative_text,
        "sha256": validated.sha256,
        "size_bytes": int(validated.size_bytes),
        "mime_type": validated.mime_type,
        "hash_algorithm": _require(
            _HASH_ALGO, validated.hash_algorithm, "HashAlgorithm"
        ),
        "session_id": (
            _require(_SESSION_ID, session_id, "SessionId")
            if session_id is not None
            else None
        ),
        "run_id": (
            _require(_RUN_ID, run_id, "RunId") if run_id is not None else None
        ),
        "run_order": run_order,
    }


def artifact_ref_from_row(row: Any) -> ArtifactRef:
    """Rebuild an ``ArtifactRef`` from an ``ArtifactORM`` row."""
    return ArtifactRef(
        artifact_id=row.artifact_id,
        artifact_type=row.artifact_type,
        relative_path=Path(row.relative_path),
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        mime_type=row.mime_type,
        hash_algorithm=row.hash_algorithm,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def profile_to_row_values(
    profile: ProfileRecord, *, data_dir: Path
) -> dict[str, object]:
    """Produce profile row values; never persists ``active_lock_path``."""
    profile_id = _require(_PROFILE_ID, profile.profile_id, "ProfileId")
    name = profile.name.strip()
    if not name:
        raise PersistenceIntegrityError("profile name must not be empty")
    health = _require(_HEALTH_STATUS, profile.health_status, "HealthStatus")
    return {
        "profile_id": profile_id,
        "name": name,
        "profile_dir": _profile_dir_to_relative(
            profile.profile_dir, data_dir=data_dir
        ),
        "fingerprint_profile_id": profile.fingerprint_profile_id,
        "proxy_profile_id": profile.proxy_profile_id,
        "health_status": health,
        "archived": profile.archived,
    }


def profile_from_row(row: Any, *, data_dir: Path) -> ProfileRecord:
    """Rebuild a ``ProfileRecord`` with ``active_lock_path=None``."""
    return ProfileRecord(
        profile_id=row.profile_id,
        name=row.name,
        profile_dir=_profile_dir_from_relative(row.profile_dir, data_dir=data_dir),
        fingerprint_profile_id=row.fingerprint_profile_id,
        proxy_profile_id=row.proxy_profile_id,
        active_lock_path=None,
        health_status=row.health_status,
        archived=row.archived,
        created_at=from_db_datetime(row.created_at) or to_utc(row.created_at),
        updated_at=from_db_datetime(row.updated_at),
    )


# ---------------------------------------------------------------------------
# Session config projection (live-model secret detection)
# ---------------------------------------------------------------------------


def persistable_session_config(config: SessionConfig) -> JsonObject:
    """Project a ``SessionConfig`` into a secret-free, allow-listed JSON object.

    Inspects the live Pydantic object — never ``model_dump`` — because
    ``SecretStr`` masks in dumps. Any secret-bearing or path-bearing field
    raises ``PersistenceSecurityError``. The result is minimal and
    deterministic.
    """
    launch = config.launch
    context = config.context

    # --- Reject secret/path-bearing launch fields. ---
    if launch.env:
        raise PersistenceSecurityError("session config launch.env must be empty")
    if launch.executable_path is not None:
        raise PersistenceSecurityError(
            "session config launch.executable_path is not persistable"
        )
    if launch.user_data_dir is not None:
        raise PersistenceSecurityError(
            "session config launch.user_data_dir is not persistable"
        )

    proxy_projection: JsonObject | None = None
    if launch.proxy is not None:
        if launch.proxy.password is not None:
            raise PersistenceSecurityError(
                "session config proxy password is not persistable"
            )
        proxy_projection = {
            "server": launch.proxy.server,
            "username": launch.proxy.username,
            "bypass": launch.proxy.bypass,
            "profile_id": launch.proxy.profile_id,
        }

    fingerprint_projection: JsonObject | None = None
    if launch.fingerprint is not None:
        if launch.fingerprint.extra:
            raise PersistenceSecurityError(
                "session config fingerprint.extra is not persistable"
            )
        fingerprint_projection = {
            "profile_id": launch.fingerprint.profile_id,
            "locale": launch.fingerprint.locale,
            "timezone_id": launch.fingerprint.timezone_id,
        }

    # --- Reject sensitive/path-bearing context fields. ---
    for header_name in context.extra_http_headers:
        if is_sensitive_header(header_name) or is_sensitive_key(header_name):
            raise PersistenceSecurityError(
                "session config contains sensitive HTTP headers"
            )
    if context.record_har_path is not None:
        raise PersistenceSecurityError(
            "session config context.record_har_path is not persistable"
        )
    if context.record_video_dir is not None:
        raise PersistenceSecurityError(
            "session config context.record_video_dir is not persistable"
        )

    viewport_projection: JsonObject | None = None
    if context.viewport is not None:
        viewport_projection = {
            "width": context.viewport.width,
            "height": context.viewport.height,
            "device_scale_factor": context.viewport.device_scale_factor,
            "is_mobile": context.viewport.is_mobile,
            "has_touch": context.viewport.has_touch,
            "preset": context.viewport.preset,
        }

    projection: JsonObject = {
        "launch": {
            "engine_name": launch.engine_name,
            "mode": launch.mode,
            "slow_mo_ms": launch.slow_mo_ms,
            "timeout_ms": launch.timeout_ms,
            "args": list(launch.args),
            "enable_tracing": launch.enable_tracing,
            "enable_video": launch.enable_video,
            "enable_console_capture": launch.enable_console_capture,
            "proxy": proxy_projection,
            "fingerprint": fingerprint_projection,
        },
        "context": {
            "viewport": viewport_projection,
            "locale": context.locale,
            "timezone_id": context.timezone_id,
            "user_agent": context.user_agent,
            "color_scheme": context.color_scheme,
            "reduced_motion": context.reduced_motion,
            "environment_profile_id": context.environment_profile_id,
            "accept_downloads": context.accept_downloads,
            "java_script_enabled": context.java_script_enabled,
            "ignore_https_errors": context.ignore_https_errors,
            "default_timeout_ms": context.default_timeout_ms,
            "navigation_timeout_ms": context.navigation_timeout_ms,
            "permissions": list(context.permissions),
            "extra_http_headers": dict(context.extra_http_headers),
        },
        "persist_storage_state": config.persist_storage_state,
        "capture_initial_storage_state": config.capture_initial_storage_state,
        "capture_final_storage_state": config.capture_final_storage_state,
        "screenshot_on_failure": config.screenshot_on_failure,
        "trace_on_failure": config.trace_on_failure,
    }
    return projection


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def session_to_row_values(session: SessionRecord) -> dict[str, object]:
    """Produce session row values, projecting config through the allow-list."""
    session_id = _require(_SESSION_ID, session.session_id, "SessionId")
    profile_id = _require(_PROFILE_ID, session.profile_id, "ProfileId")
    name = session.name.strip()
    if not name:
        raise PersistenceIntegrityError("session name must not be empty")
    health = _require(_HEALTH_STATUS, session.health_status, "HealthStatus")
    projection = persistable_session_config(session.config)
    return {
        "session_id": session_id,
        "name": name,
        "profile_id": profile_id,
        "config_json": canonical_json(projection),
        "latest_initial_artifact_id": (
            session.latest_initial_state.artifact_id
            if session.latest_initial_state is not None
            else None
        ),
        "latest_final_artifact_id": (
            session.latest_final_state.artifact_id
            if session.latest_final_state is not None
            else None
        ),
        "health_status": health,
        "archived": session.archived,
    }


def session_from_row(
    row: Any,
    *,
    latest_initial: ArtifactRef | None,
    latest_final: ArtifactRef | None,
) -> SessionRecord:
    """Rebuild a ``SessionRecord`` from a session row + rehydrated refs.

    The persisted config is the allow-listed projection rebuilt into a minimal
    ``SessionConfig``; secret/path-bearing fields were never stored.
    """
    projection = decode_json_object(row.config_json)
    config = _session_config_from_projection(projection)
    return SessionRecord(
        session_id=row.session_id,
        name=row.name,
        profile_id=row.profile_id,
        config=config,
        latest_initial_state=latest_initial,
        latest_final_state=latest_final,
        health_status=row.health_status,
        archived=row.archived,
        created_at=to_utc(row.created_at),
        updated_at=from_db_datetime(row.updated_at),
    )


def _as_object(value: Any) -> dict[str, Any]:
    """Return ``value`` as a ``dict[str, Any]`` or raise if it is not a mapping."""
    if not isinstance(value, dict):
        raise PersistenceIntegrityError("stored session config is malformed")
    return {str(k): v for k, v in value.items()}  # type: ignore[misc]


def _session_config_from_projection(projection: JsonObject) -> SessionConfig:
    """Rebuild a minimal ``SessionConfig`` from a stored projection."""
    from sightstalker.models import (
        BrowserContextConfig,
        BrowserLaunchConfig,
        FingerprintConfig,
        ProxyConfig,
        ViewportConfig,
    )

    launch_proj = _as_object(projection.get("launch", {}))
    context_proj = _as_object(projection.get("context", {}))

    proxy_raw: Any = launch_proj.get("proxy")
    proxy = None
    if isinstance(proxy_raw, dict):
        proxy_proj = _as_object(proxy_raw)
        proxy = ProxyConfig(
            server=str(proxy_proj.get("server", "")),
            username=_opt_str(proxy_proj.get("username")),
            bypass=_opt_str(proxy_proj.get("bypass")),
            profile_id=_opt_str(proxy_proj.get("profile_id")),
        )

    fp_raw: Any = launch_proj.get("fingerprint")
    fingerprint = None
    if isinstance(fp_raw, dict):
        fp_proj = _as_object(fp_raw)
        fingerprint = FingerprintConfig(
            profile_id=_opt_str(fp_proj.get("profile_id")),
            locale=_opt_str(fp_proj.get("locale")),
            timezone_id=_opt_str(fp_proj.get("timezone_id")),
        )

    launch = BrowserLaunchConfig(
        engine_name=str(launch_proj.get("engine_name", "camoufox")),  # type: ignore[arg-type]
        mode=str(launch_proj.get("mode", "headless")),  # type: ignore[arg-type]
        slow_mo_ms=int(launch_proj.get("slow_mo_ms", 0)),
        timeout_ms=int(launch_proj.get("timeout_ms", 30_000)),
        args=tuple(str(a) for a in _as_list(launch_proj.get("args", []))),
        enable_tracing=bool(launch_proj.get("enable_tracing", False)),
        enable_video=bool(launch_proj.get("enable_video", False)),
        enable_console_capture=bool(
            launch_proj.get("enable_console_capture", True)
        ),
        proxy=proxy,
        fingerprint=fingerprint,
    )

    vp_raw: Any = context_proj.get("viewport")
    viewport = None
    if isinstance(vp_raw, dict):
        vp_proj = _as_object(vp_raw)
        viewport = ViewportConfig(
            width=int(vp_proj["width"]),
            height=int(vp_proj["height"]),
            device_scale_factor=float(vp_proj.get("device_scale_factor", 1.0)),
            is_mobile=bool(vp_proj.get("is_mobile", False)),
            has_touch=bool(vp_proj.get("has_touch", False)),
            preset=str(vp_proj.get("preset", "custom")),  # type: ignore[arg-type]
        )

    context = BrowserContextConfig(
        viewport=viewport,
        locale=_opt_str(context_proj.get("locale")),
        timezone_id=_opt_str(context_proj.get("timezone_id")),
        user_agent=_opt_str(context_proj.get("user_agent")),
        color_scheme=_opt_color_scheme(context_proj.get("color_scheme")),
        reduced_motion=_opt_reduced_motion(context_proj.get("reduced_motion")),
        environment_profile_id=_opt_str(
            context_proj.get("environment_profile_id")
        ),
        accept_downloads=bool(context_proj.get("accept_downloads", False)),
        java_script_enabled=bool(context_proj.get("java_script_enabled", True)),
        ignore_https_errors=bool(context_proj.get("ignore_https_errors", False)),
        default_timeout_ms=int(context_proj.get("default_timeout_ms", 30_000)),
        navigation_timeout_ms=int(
            context_proj.get("navigation_timeout_ms", 45_000)
        ),
        permissions=tuple(
            str(p) for p in _as_list(context_proj.get("permissions", []))
        ),
        extra_http_headers={
            str(k): str(v)
            for k, v in _as_object(
                context_proj.get("extra_http_headers", {})
            ).items()
        },
    )

    return SessionConfig(
        launch=launch,
        context=context,
        persist_storage_state=bool(projection.get("persist_storage_state", True)),
        capture_initial_storage_state=bool(
            projection.get("capture_initial_storage_state", True)
        ),
        capture_final_storage_state=bool(
            projection.get("capture_final_storage_state", True)
        ),
        screenshot_on_failure=bool(projection.get("screenshot_on_failure", True)),
        trace_on_failure=bool(projection.get("trace_on_failure", True)),
    )


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_color_scheme(
    value: Any,
) -> Literal["light", "dark", "no-preference"] | None:
    if value is None:
        return None
    text = str(value)
    if text in ("light", "dark", "no-preference"):
        return text  # type: ignore[return-value]
    return None


def _opt_reduced_motion(
    value: Any,
) -> Literal["reduce", "no-preference"] | None:
    if value is None:
        return None
    text = str(value)
    if text in ("reduce", "no-preference"):
        return text  # type: ignore[return-value]
    return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)  # type: ignore[arg-type]
    return []


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _reject_url_credentials(start_url: str | None) -> str | None:
    if start_url is None:
        return None
    try:
        parts = urlsplit(start_url)
    except ValueError:
        raise PersistenceIntegrityError("start_url is malformed") from None
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        raise PersistenceSecurityError(
            "start_url must not contain embedded credentials"
        )
    return start_url


def run_to_row_values(run: RunRecord) -> dict[str, object]:
    """Produce run row values; redacts metadata and error text, scalar only."""
    run_id = _require(_RUN_ID, run.run_id, "RunId")
    session_id = _require(_SESSION_ID, run.session_id, "SessionId")
    status = _require(_RUN_STATUS, run.status, "RunStatus")
    redacted_metadata = redact_mapping(run.metadata)
    error_message = (
        redact_string(run.error_message_redacted)
        if run.error_message_redacted is not None
        else None
    )
    return {
        "run_id": run_id,
        "session_id": session_id,
        "status": status,
        "started_at": to_utc(run.started_at) if run.started_at else None,
        "completed_at": to_utc(run.completed_at) if run.completed_at else None,
        "start_url": _reject_url_credentials(run.start_url),
        "error_type": run.error_type,
        "error_message_redacted": error_message,
        "metadata_json": canonical_json(redacted_metadata),
    }


def run_from_row(row: Any, *, artifacts: tuple[ArtifactRef, ...]) -> RunRecord:
    """Rebuild a ``RunRecord`` from a run row + ordered artifact refs."""
    metadata = decode_json_object(row.metadata_json)
    return RunRecord(
        run_id=row.run_id,
        session_id=row.session_id,
        status=row.status,
        started_at=from_db_datetime(row.started_at),
        completed_at=from_db_datetime(row.completed_at),
        start_url=row.start_url,
        error_type=row.error_type,
        error_message_redacted=row.error_message_redacted,
        artifacts=artifacts,
        metadata=metadata,
        created_at=to_utc(row.created_at),
        updated_at=from_db_datetime(row.updated_at),
    )


# ---------------------------------------------------------------------------
# Browser context
# ---------------------------------------------------------------------------


def context_to_row_values(context: BrowserContextRecord) -> dict[str, object]:
    """Produce browser-context row values (artifact IDs only)."""
    context_id = _require(_CONTEXT_ID, context.context_id, "ContextId")
    return {
        "context_id": context_id,
        "run_id": _require(_RUN_ID, context.run_id, "RunId"),
        "session_id": _require(_SESSION_ID, context.session_id, "SessionId"),
        "initial_storage_artifact_id": (
            context.initial_storage_state.artifact_id
            if context.initial_storage_state is not None
            else None
        ),
        "final_storage_artifact_id": (
            context.final_storage_state.artifact_id
            if context.final_storage_state is not None
            else None
        ),
        "closed_at": to_utc(context.closed_at) if context.closed_at else None,
    }


def context_from_row(
    row: Any,
    *,
    initial: ArtifactRef | None,
    final: ArtifactRef | None,
) -> BrowserContextRecord:
    """Rebuild a ``BrowserContextRecord`` from a context row + refs."""
    return BrowserContextRecord(
        context_id=row.context_id,
        run_id=row.run_id,
        session_id=row.session_id,
        initial_storage_state=initial,
        final_storage_state=final,
        closed_at=from_db_datetime(row.closed_at),
        created_at=to_utc(row.created_at),
        updated_at=from_db_datetime(row.updated_at),
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def health_to_row_values(record: SessionHealthRecord) -> dict[str, object]:
    """Produce health row values; sanitizes ``reason``."""
    session_id = _require(_SESSION_ID, record.session_id, "SessionId")
    status = _require(_HEALTH_STATUS, record.status, "HealthStatus")
    reason = redact_string(record.reason) if record.reason is not None else None
    return {
        "session_id": session_id,
        "status": status,
        "reason": reason,
        "last_successful_run_id": record.last_successful_run_id,
        "last_failed_run_id": record.last_failed_run_id,
    }


def health_from_row(row: Any) -> SessionHealthRecord:
    """Rebuild a ``SessionHealthRecord`` (DB ``id`` is not surfaced)."""
    return SessionHealthRecord(
        session_id=row.session_id,
        status=row.status,
        reason=row.reason,
        last_successful_run_id=row.last_successful_run_id,
        last_failed_run_id=row.last_failed_run_id,
        created_at=to_utc(row.created_at),
        updated_at=from_db_datetime(row.updated_at),
    )
