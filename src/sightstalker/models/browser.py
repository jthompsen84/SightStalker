from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator

from sightstalker.models.base import JsonObject, ToolkitModel
from sightstalker.models.identifiers import (
    BrowserEngineName,
    BrowserMode,
    FingerprintProfileId,
    ProxyProfileId,
)

# ---------------------------------------------------------------------------
# Viewport
# ---------------------------------------------------------------------------

ViewportPreset = Literal[
    "desktop_1366x768",
    "desktop_1440x900",
    "desktop_1920x1080",
    "mobile_390x844",
    "custom",
]


def validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    """Shared validator for identity-adjacent optional text fields.

    Used for ``user_agent`` (and reused by environment override/profile models)
    so the rule is identical everywhere: ``None`` is allowed, but a present
    value must be non-empty after stripping and must contain no NUL/control
    characters.
    """
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if any(ord(ch) < 32 or ch == "\x7f" for ch in value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


class ViewportConfig(ToolkitModel):
    """Browser viewport dimensions and device characteristics."""

    width: int = Field(ge=320, le=7680)
    height: int = Field(ge=320, le=4320)
    device_scale_factor: float = Field(default=1.0, ge=0.5, le=4.0)
    is_mobile: bool = False
    has_touch: bool = False
    preset: ViewportPreset = "custom"


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------


class ProxyConfig(ToolkitModel):
    """
    Runtime proxy configuration.

    Sensitive values use SecretStr and are excluded from repr.
    This object may exist in memory but must not be logged raw.
    Callers must use redact_mapping before logging any proxy-related dict.
    """

    server: str
    username: str | None = None
    password: SecretStr | None = Field(default=None, repr=False)
    bypass: str | None = None
    profile_id: ProxyProfileId | None = None


# ---------------------------------------------------------------------------
# Fingerprint / environment profile reference
# ---------------------------------------------------------------------------


class FingerprintConfig(ToolkitModel):
    """
    Reference to a fingerprint/environment profile.

    This model carries a stable profile reference and selected runtime knobs.
    Raw fingerprint material lives in JSON artifacts, not here.
    This is a config reference model — not a fingerprint generation system.
    Do not add fingerprint randomization or stealth claims here.
    """

    profile_id: FingerprintProfileId | None = None
    locale: str | None = None
    timezone_id: str | None = None
    user_agent: str | None = Field(default=None, repr=False)
    extra: JsonObject = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Browser launch configuration
# ---------------------------------------------------------------------------


class BrowserLaunchConfig(ToolkitModel):
    """
    Immutable configuration for launching a browser runtime.

    This model does not launch anything. It is the stable config object
    passed to BrowserEngine.launch(). Sensitive fields (env) are excluded
    from repr to prevent accidental secret logging.
    """

    engine_name: BrowserEngineName = "camoufox"
    mode: BrowserMode = "headless"
    executable_path: Path | None = None
    user_data_dir: Path | None = None
    slow_mo_ms: int = Field(default=0, ge=0, le=10_000)
    timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    proxy: ProxyConfig | None = None
    fingerprint: FingerprintConfig | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = Field(default_factory=dict, repr=False)
    enable_tracing: bool = False
    enable_video: bool = False
    enable_console_capture: bool = True


# ---------------------------------------------------------------------------
# Browser context configuration
# ---------------------------------------------------------------------------


class BrowserContextConfig(ToolkitModel):
    """
    Immutable configuration for one browser isolation context.

    Context config is separate from launch config because one launched runtime
    may create multiple isolated contexts. Sensitive fields (extra_http_headers)
    are excluded from repr.
    """

    viewport: ViewportConfig | None = None
    locale: str | None = None
    timezone_id: str | None = None
    user_agent: str | None = Field(default=None, repr=False)
    color_scheme: Literal["light", "dark", "no-preference"] | None = None
    reduced_motion: Literal["reduce", "no-preference"] | None = None
    environment_profile_id: FingerprintProfileId | None = None
    accept_downloads: bool = False
    java_script_enabled: bool = True
    ignore_https_errors: bool = False
    default_timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    navigation_timeout_ms: int = Field(default=45_000, ge=1_000, le=300_000)
    extra_http_headers: dict[str, str] = Field(default_factory=dict, repr=False)
    permissions: tuple[str, ...] = ()
    record_har_path: Path | None = None
    record_video_dir: Path | None = None

    @field_validator("user_agent")
    @classmethod
    def _validate_user_agent(cls, value: str | None) -> str | None:
        return validate_optional_text(value, field_name="user_agent")


# ---------------------------------------------------------------------------
# Browser state snapshot
# ---------------------------------------------------------------------------


class BrowserState(ToolkitModel):
    """
    Portable, immutable browser state snapshot.

    cookies and origins are tuple-backed to prevent top-level mutation such as
    state.cookies.append(...). Nested browser-emitted JSON dicts are not
    deeply frozen in this layer; callers must treat the entire object as a
    read-only snapshot and must not mutate nested payloads.

    This model is not stored directly in SQL rows. It is serialized to a JSON
    artifact file and referenced by an ArtifactRef.
    """

    cookies: tuple[JsonObject, ...] = Field(default=(), repr=False)
    origins: tuple[JsonObject, ...] = Field(default=(), repr=False)
    indexed_db_included: bool = False
    engine_name: BrowserEngineName
    schema_version: str = "browser_state_v1"
