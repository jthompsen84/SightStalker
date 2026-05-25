"""
sightstalker.environment.resolver — DefaultContextConfigResolver.

Produces immutable effective ``BrowserLaunchConfig`` / ``BrowserContextConfig``
from session defaults, a selected environment profile, and run-tier overrides,
with binding precedence:

    run override > selected environment profile > session default > package default

The resolver never mutates session config, never calls engine_factory or
SessionManager, and never imports CLI or Camoufox/Playwright.
"""

from __future__ import annotations

from sightstalker.environment.applicators import (
    ENVIRONMENT_CONTEXT_FIELDS,
    DefaultEnvironmentProfileApplicator,
)
from sightstalker.environment.models import (
    ContextConfigResolution,
    RunConfigOverrides,
)
from sightstalker.environment.protocols import (
    EnvironmentProfileApplicator,
    EnvironmentProfileSelector,
    EnvironmentProfileStore,
)
from sightstalker.environment.selectors import DefaultEnvironmentProfileSelector
from sightstalker.environment.stores import NullEnvironmentProfileStore
from sightstalker.models.browser import BrowserContextConfig, BrowserLaunchConfig
from sightstalker.models.runs import RunRequest
from sightstalker.models.sessions import ProfileRecord, SessionRecord

_LAUNCH_OVERRIDE_FIELDS: tuple[str, ...] = ("mode", "slow_mo_ms", "timeout_ms")
_CONTEXT_OVERRIDE_FIELDS: tuple[str, ...] = (
    "user_agent",
    "viewport",
    "locale",
    "timezone_id",
    "color_scheme",
    "reduced_motion",
    "default_timeout_ms",
    "navigation_timeout_ms",
)


class DefaultContextConfigResolver:
    """Resolve effective launch/context config before engine launch."""

    def __init__(
        self,
        *,
        store: EnvironmentProfileStore | None = None,
        selector: EnvironmentProfileSelector | None = None,
        applicator: EnvironmentProfileApplicator | None = None,
    ) -> None:
        self._store: EnvironmentProfileStore = (
            store if store is not None else NullEnvironmentProfileStore()
        )
        self._selector: EnvironmentProfileSelector = (
            selector if selector is not None
            else DefaultEnvironmentProfileSelector()
        )
        self._applicator: EnvironmentProfileApplicator = (
            applicator if applicator is not None
            else DefaultEnvironmentProfileApplicator()
        )

    async def resolve(
        self,
        *,
        profile: ProfileRecord,
        session: SessionRecord,
        request: RunRequest,
        overrides: RunConfigOverrides | None = None,
    ) -> ContextConfigResolution:
        launch: BrowserLaunchConfig = session.config.launch
        context: BrowserContextConfig = session.config.context

        env_overrides = overrides.environment if overrides is not None else None

        # 1. Select environment profile id.
        selected_id = await self._selector.select(
            profile=profile,
            session=session,
            request=request,
            overrides=env_overrides,
        )

        # 2. Apply selected profile (if any) onto the context.
        context_after_env = context
        env_contributed: dict[str, object] = {}
        if selected_id is not None:
            environment = await self._store.load(selected_id)
            context_after_env = self._applicator.apply(
                base=context, environment=environment
            )
            for field in ENVIRONMENT_CONTEXT_FIELDS:
                value = getattr(environment, field)
                if value is not None:
                    env_contributed[field] = value

        # 3. Apply run-tier overrides last (highest precedence).
        launch_updates: dict[str, object] = {}
        context_updates: dict[str, object] = {}
        overridden_context_fields: set[str] = set()
        if overrides is not None:
            if overrides.launch is not None:
                for field in _LAUNCH_OVERRIDE_FIELDS:
                    value = getattr(overrides.launch, field)
                    if value is not None:
                        launch_updates[field] = value
            if overrides.context is not None:
                for field in _CONTEXT_OVERRIDE_FIELDS:
                    value = getattr(overrides.context, field)
                    if value is not None:
                        context_updates[field] = value
                        overridden_context_fields.add(field)

        effective_launch = (
            launch.model_copy(update=launch_updates) if launch_updates else launch
        )
        effective_context = (
            context_after_env.model_copy(update=context_updates)
            if context_updates
            else context_after_env
        )

        # 4. applied_environment_fields = profile-contributed fields whose final
        #    effective value was NOT replaced by a run override.
        applied = tuple(
            sorted(
                field
                for field in env_contributed
                if field not in overridden_context_fields
            )
        )

        return ContextConfigResolution(
            launch=effective_launch,
            context=effective_context,
            environment_profile_id=selected_id,
            applied_environment_fields=applied,
        )


__all__ = ["DefaultContextConfigResolver"]
