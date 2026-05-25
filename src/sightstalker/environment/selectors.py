"""
sightstalker.environment.selectors — environment profile selection.

Default selection precedence:
  1. explicit run/programmatic override environment_profile_id,
  2. session.config.context.environment_profile_id,
  3. None.

ENVIRONMENT-1 does NOT default-select from ``ProfileRecord.fingerprint_profile_id``
(operator decision); that legacy field stays inert.
"""

from __future__ import annotations

from sightstalker.environment.models import EnvironmentResolutionOverrides
from sightstalker.models.identifiers import FingerprintProfileId
from sightstalker.models.runs import RunRequest
from sightstalker.models.sessions import ProfileRecord, SessionRecord


class NullEnvironmentProfileSelector:
    """Never selects a profile."""

    async def select(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: EnvironmentResolutionOverrides | None = None,
    ) -> FingerprintProfileId | None:
        return None


class StaticEnvironmentProfileSelector:
    """Always selects a fixed profile id (programmatic/testing)."""

    def __init__(self, profile_id: FingerprintProfileId) -> None:
        self._profile_id = profile_id

    async def select(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: EnvironmentResolutionOverrides | None = None,
    ) -> FingerprintProfileId | None:
        return self._profile_id


class SessionContextEnvironmentProfileSelector:
    """Selects ``session.config.context.environment_profile_id`` if set."""

    async def select(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: EnvironmentResolutionOverrides | None = None,
    ) -> FingerprintProfileId | None:
        return session.config.context.environment_profile_id


class DefaultEnvironmentProfileSelector:
    """Override id, then session context profile id, then None."""

    async def select(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: EnvironmentResolutionOverrides | None = None,
    ) -> FingerprintProfileId | None:
        if overrides is not None and overrides.environment_profile_id is not None:
            return overrides.environment_profile_id
        return session.config.context.environment_profile_id


__all__ = [
    "DefaultEnvironmentProfileSelector",
    "NullEnvironmentProfileSelector",
    "SessionContextEnvironmentProfileSelector",
    "StaticEnvironmentProfileSelector",
]
