"""Resolver precedence, immutability, and applied-fields tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sightstalker.environment.errors import EnvironmentProfileNotFound
from sightstalker.environment.models import (
    ContextConfigOverrides,
    EnvironmentProfile,
    LaunchConfigOverrides,
    RunConfigOverrides,
)
from sightstalker.environment.resolver import DefaultContextConfigResolver
from sightstalker.environment.selectors import (
    DefaultEnvironmentProfileSelector,
    StaticEnvironmentProfileSelector,
)
from sightstalker.environment.stores import InMemoryEnvironmentProfileStore
from sightstalker.models.browser import BrowserContextConfig, BrowserLaunchConfig
from sightstalker.models.runs import RunRequest
from sightstalker.models.sessions import ProfileRecord, SessionConfig, SessionRecord

_SESS = "sess_test_00000001"
_PROF = "prof_test_00000001"
_ENV = "fp_test_00000001"


def _session(
    *, context: BrowserContextConfig | None = None,
    launch: BrowserLaunchConfig | None = None,
) -> SessionRecord:
    config = SessionConfig(
        launch=launch or BrowserLaunchConfig(),
        context=context or BrowserContextConfig(),
    )
    return SessionRecord(
        session_id=_SESS, name="s", profile_id=_PROF, config=config
    )


def _profile_record() -> ProfileRecord:
    return ProfileRecord(profile_id=_PROF, name="p", profile_dir=Path("/tmp/p"))


def _request() -> RunRequest:
    return RunRequest(session_id=_SESS)


def _env_profile(**kw: object) -> EnvironmentProfile:
    base: dict[str, object] = {"profile_id": _ENV, "name": "desktop"}
    base.update(kw)
    return EnvironmentProfile(**base)  # type: ignore[arg-type]


def _resolver(profile: EnvironmentProfile | None) -> DefaultContextConfigResolver:
    store = InMemoryEnvironmentProfileStore([profile] if profile else [])
    selector = (
        StaticEnvironmentProfileSelector(_ENV)
        if profile is not None
        else DefaultEnvironmentProfileSelector()
    )
    return DefaultContextConfigResolver(store=store, selector=selector)


async def test_no_profile_returns_session_defaults() -> None:
    resolver = DefaultContextConfigResolver()
    session = _session(context=BrowserContextConfig(locale="fr-FR"))
    resolution = await resolver.resolve(
        profile=_profile_record(), session=session, request=_request()
    )
    assert resolution.context.locale == "fr-FR"
    assert resolution.environment_profile_id is None
    assert resolution.applied_environment_fields == ()


async def test_environment_profile_overrides_session_default() -> None:
    resolver = _resolver(_env_profile(locale="en-US", user_agent="UA/1.0"))
    session = _session(context=BrowserContextConfig(locale="fr-FR"))
    resolution = await resolver.resolve(
        profile=_profile_record(), session=session, request=_request()
    )
    assert resolution.context.locale == "en-US"
    assert resolution.context.user_agent == "UA/1.0"
    assert resolution.environment_profile_id == _ENV
    assert "locale" in resolution.applied_environment_fields
    assert "user_agent" in resolution.applied_environment_fields


async def test_run_override_wins_over_environment_profile() -> None:
    resolver = _resolver(_env_profile(locale="en-US"))
    session = _session()
    overrides = RunConfigOverrides(
        context=ContextConfigOverrides(locale="de-DE")
    )
    resolution = await resolver.resolve(
        profile=_profile_record(),
        session=session,
        request=_request(),
        overrides=overrides,
    )
    assert resolution.context.locale == "de-DE"
    # locale was overridden by run override -> excluded from applied fields.
    assert "locale" not in resolution.applied_environment_fields


async def test_applied_fields_sorted_and_exclude_overridden() -> None:
    resolver = _resolver(
        _env_profile(locale="en-US", timezone_id="UTC", color_scheme="dark")
    )
    overrides = RunConfigOverrides(
        context=ContextConfigOverrides(color_scheme="light")
    )
    resolution = await resolver.resolve(
        profile=_profile_record(),
        session=_session(),
        request=_request(),
        overrides=overrides,
    )
    assert resolution.applied_environment_fields == ("locale", "timezone_id")
    assert resolution.context.color_scheme == "light"


async def test_resolver_does_not_mutate_session_config() -> None:
    resolver = _resolver(_env_profile(locale="en-US"))
    session = _session(context=BrowserContextConfig(locale="fr-FR"))
    original_locale = session.config.context.locale
    await resolver.resolve(
        profile=_profile_record(), session=session, request=_request()
    )
    assert session.config.context.locale == original_locale == "fr-FR"


async def test_launch_override_applied() -> None:
    resolver = DefaultContextConfigResolver()
    overrides = RunConfigOverrides(launch=LaunchConfigOverrides(mode="headed"))
    resolution = await resolver.resolve(
        profile=_profile_record(),
        session=_session(),
        request=_request(),
        overrides=overrides,
    )
    assert resolution.launch.mode == "headed"


async def test_missing_profile_raises_not_found() -> None:
    # Selector points at an id the store does not contain.
    store = InMemoryEnvironmentProfileStore()
    resolver = DefaultContextConfigResolver(
        store=store, selector=StaticEnvironmentProfileSelector(_ENV)
    )
    with pytest.raises(EnvironmentProfileNotFound):
        await resolver.resolve(
            profile=_profile_record(), session=_session(), request=_request()
        )


async def test_returned_configs_are_new_objects() -> None:
    resolver = _resolver(_env_profile(locale="en-US"))
    session = _session()
    resolution = await resolver.resolve(
        profile=_profile_record(), session=session, request=_request()
    )
    assert resolution.context is not session.config.context
