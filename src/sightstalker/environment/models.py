"""
sightstalker.environment.models — environment profile and resolution contracts.

These are declarative configuration data contracts. They are not fingerprint
generators, proxy rotators, browser-state payloads, identity randomizers, or
behavior simulators. ``ENVIRONMENT-1`` validates them and resolves effective
launch/context config from them; it never injects scripts, mutates pages, or
generates identity material.

Public override/resolution models live here (not in ``resolver.py``) so that
``protocols.py`` and ``resolver.py`` can both import them without an import
cycle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from sightstalker.models.base import ToolkitModel
from sightstalker.models.browser import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserMode,
    ViewportConfig,
    validate_optional_text,
)
from sightstalker.models.identifiers import FingerprintProfileId

ColorScheme = Literal["light", "dark", "no-preference"]
ReducedMotion = Literal["reduce", "no-preference"]


def validate_user_agent(value: str | None) -> str | None:
    """Shared user-agent validation (delegates to the base model rule)."""
    return validate_optional_text(value, field_name="user_agent")


class NavigatorProfile(ToolkitModel):
    """Forward-reserved declarative navigator-shaped metadata.

    ENVIRONMENT-1 validates this metadata but never applies it, injects it,
    persists it to SQL config JSON, or uses it to mutate contexts/pages. There
    is intentionally no free-form ``extra`` bucket in this PR.
    """

    platform: str | None = None
    languages: tuple[str, ...] = ()
    hardware_concurrency: int | None = Field(default=None, ge=1, le=256)
    device_memory_gb: float | None = Field(default=None, ge=0.25, le=1024)

    @field_validator("languages")
    @classmethod
    def _validate_languages(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for entry in value:
            if not entry.strip():
                raise ValueError("navigator languages entries must not be empty")
        return value


class EnvironmentProfile(ToolkitModel):
    """Declarative environment profile.

    Configuration data only: not a fingerprint generator, proxy rotator, browser
    state payload, identity randomizer, or behavior simulator. ``profile_id``
    uses the legacy ``fp_`` ID type (``FingerprintProfileId``); this is accepted
    legacy naming debt and does not imply fingerprint capability.
    """

    profile_id: FingerprintProfileId
    name: str
    description: str | None = None

    user_agent: str | None = Field(default=None, repr=False)
    viewport: ViewportConfig | None = None
    locale: str | None = None
    timezone_id: str | None = None
    color_scheme: ColorScheme | None = None
    reduced_motion: ReducedMotion | None = None

    navigator: NavigatorProfile | None = None
    schema_version: str = "environment_profile_v1"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value

    @field_validator("user_agent")
    @classmethod
    def _validate_user_agent(cls, value: str | None) -> str | None:
        return validate_user_agent(value)

    @field_validator("locale")
    @classmethod
    def _validate_locale(cls, value: str | None) -> str | None:
        return validate_optional_text(value, field_name="locale")

    @field_validator("timezone_id")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        return validate_optional_text(value, field_name="timezone_id")

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: str) -> str:
        if value != "environment_profile_v1":
            raise ValueError("schema_version must be environment_profile_v1")
        return value


# Internal compatibility alias only. Do not export from __all__.
# FingerprintProfileId / fp_ prefixes are legacy naming debt from earlier
# contracts; they do not imply fingerprint generation or fingerprint capability
# in ENVIRONMENT-1.
FingerprintProfile = EnvironmentProfile


class LaunchConfigOverrides(ToolkitModel):
    """Run-tier overrides for launch config (programmatic; no CLI flags)."""

    mode: BrowserMode | None = None
    slow_mo_ms: int | None = Field(default=None, ge=0, le=10_000)
    timeout_ms: int | None = Field(default=None, ge=1_000, le=300_000)


class ContextConfigOverrides(ToolkitModel):
    """Run-tier overrides for context config (programmatic; no CLI flags)."""

    user_agent: str | None = Field(default=None, repr=False)
    viewport: ViewportConfig | None = None
    locale: str | None = None
    timezone_id: str | None = None
    color_scheme: ColorScheme | None = None
    reduced_motion: ReducedMotion | None = None
    default_timeout_ms: int | None = Field(default=None, ge=1_000, le=300_000)
    navigation_timeout_ms: int | None = Field(default=None, ge=1_000, le=300_000)

    @field_validator("user_agent")
    @classmethod
    def _validate_user_agent(cls, value: str | None) -> str | None:
        return validate_user_agent(value)


class EnvironmentResolutionOverrides(ToolkitModel):
    """Run-tier override selecting an environment profile by id."""

    environment_profile_id: FingerprintProfileId | None = None


class RunConfigOverrides(ToolkitModel):
    """Composite run-tier overrides applied last in resolution precedence."""

    launch: LaunchConfigOverrides | None = None
    context: ContextConfigOverrides | None = None
    environment: EnvironmentResolutionOverrides | None = None


class ContextConfigResolution(ToolkitModel):
    """Immutable effective config produced by a ContextConfigResolver.

    ``applied_environment_fields`` lists, lexicographically sorted, the context
    fields whose final effective value came from the selected environment
    profile after run overrides were applied. It is in-memory provenance only
    and is never persisted.
    """

    launch: BrowserLaunchConfig
    context: BrowserContextConfig
    environment_profile_id: FingerprintProfileId | None = None
    applied_environment_fields: tuple[str, ...] = ()


__all__ = [
    "ColorScheme",
    "ContextConfigOverrides",
    "ContextConfigResolution",
    "EnvironmentProfile",
    "EnvironmentResolutionOverrides",
    "LaunchConfigOverrides",
    "NavigatorProfile",
    "ReducedMotion",
    "RunConfigOverrides",
    "validate_user_agent",
]
