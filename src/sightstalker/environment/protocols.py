"""
sightstalker.environment.protocols — store/selector/applicator/resolver contracts.

These import the public data models from ``environment.models`` (never from
``resolver.py``) so the package stays cycle-free. Importing this module must not
load Camoufox, Playwright, CLI, persistence, or sessions.manager.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sightstalker.environment.models import (
    ContextConfigResolution,
    EnvironmentProfile,
    EnvironmentResolutionOverrides,
    RunConfigOverrides,
)
from sightstalker.models.browser import BrowserContextConfig
from sightstalker.models.identifiers import FingerprintProfileId
from sightstalker.models.runs import RunRequest
from sightstalker.models.sessions import ProfileRecord, SessionRecord


@runtime_checkable
class EnvironmentProfileStore(Protocol):
    async def load(self, profile_id: FingerprintProfileId) -> EnvironmentProfile:
        ...


@runtime_checkable
class EnvironmentProfileSelector(Protocol):
    async def select(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: EnvironmentResolutionOverrides | None = None,
    ) -> FingerprintProfileId | None:
        ...


@runtime_checkable
class EnvironmentProfileApplicator(Protocol):
    def apply(
        self,
        *,
        base: BrowserContextConfig,
        environment: EnvironmentProfile,
    ) -> BrowserContextConfig:
        ...


@runtime_checkable
class ContextConfigResolver(Protocol):
    async def resolve(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: RunConfigOverrides | None = None,
    ) -> ContextConfigResolution:
        ...


__all__ = [
    "ContextConfigResolver",
    "EnvironmentProfileApplicator",
    "EnvironmentProfileSelector",
    "EnvironmentProfileStore",
]
