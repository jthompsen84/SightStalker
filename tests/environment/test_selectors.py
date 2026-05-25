"""Selector precedence tests."""

from __future__ import annotations

from typing import Any


from sightstalker.environment.models import EnvironmentResolutionOverrides
from sightstalker.environment.selectors import (
    DefaultEnvironmentProfileSelector,
    NullEnvironmentProfileSelector,
    SessionContextEnvironmentProfileSelector,
    StaticEnvironmentProfileSelector,
)
from sightstalker.models.browser import BrowserContextConfig, BrowserLaunchConfig
from sightstalker.models.runs import RunRequest
from sightstalker.models.sessions import ProfileRecord, SessionConfig, SessionRecord

_SESS_ID = "sess_test_00000001"
_PROF_ID = "prof_test_00000001"
_ENV_A = "fp_test_00000001"
_ENV_B = "fp_test_00000002"


def _session(env_id: str | None) -> SessionRecord:
    context = BrowserContextConfig(environment_profile_id=env_id)
    config = SessionConfig(launch=BrowserLaunchConfig(), context=context)
    return SessionRecord(
        session_id=_SESS_ID, name="s", profile_id=_PROF_ID, config=config
    )


def _profile() -> ProfileRecord:
    from pathlib import Path

    return ProfileRecord(
        profile_id=_PROF_ID, name="p", profile_dir=Path("/tmp/p")
    )


def _request() -> RunRequest:
    return RunRequest(session_id=_SESS_ID)


async def _select(selector: Any, env_id: str | None, overrides: Any = None) -> Any:
    return await selector.select(
        profile=_profile(),
        session=_session(env_id),
        request=_request(),
        overrides=overrides,
    )


async def test_null_selector_returns_none() -> None:
    assert await _select(NullEnvironmentProfileSelector(), _ENV_A) is None


async def test_static_selector_returns_fixed() -> None:
    assert await _select(StaticEnvironmentProfileSelector(_ENV_B), None) == _ENV_B


async def test_session_context_selector() -> None:
    sel = SessionContextEnvironmentProfileSelector()
    assert await _select(sel, _ENV_A) == _ENV_A
    assert await _select(sel, None) is None


async def test_default_override_wins_over_session() -> None:
    sel = DefaultEnvironmentProfileSelector()
    overrides = EnvironmentResolutionOverrides(environment_profile_id=_ENV_B)
    assert await _select(sel, _ENV_A, overrides) == _ENV_B


async def test_default_falls_back_to_session_context() -> None:
    sel = DefaultEnvironmentProfileSelector()
    assert await _select(sel, _ENV_A) == _ENV_A


async def test_default_returns_none_when_nothing_set() -> None:
    sel = DefaultEnvironmentProfileSelector()
    assert await _select(sel, None) is None


async def test_default_does_not_select_from_fingerprint_profile_id() -> None:
    # ENVIRONMENT-1: ProfileRecord.fingerprint_profile_id is NOT a selection
    # source. A profile carrying it must still yield None when nothing else set.
    from pathlib import Path

    profile = ProfileRecord(
        profile_id=_PROF_ID,
        name="p",
        profile_dir=Path("/tmp/p"),
        fingerprint_profile_id=_ENV_A,
    )
    sel = DefaultEnvironmentProfileSelector()
    result = await sel.select(
        profile=profile,
        session=_session(None),
        request=_request(),
        overrides=None,
    )
    assert result is None
