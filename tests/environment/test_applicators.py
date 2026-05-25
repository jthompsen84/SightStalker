"""Applicator behavior tests."""

from __future__ import annotations

from sightstalker.environment.applicators import DefaultEnvironmentProfileApplicator
from sightstalker.environment.models import EnvironmentProfile, NavigatorProfile
from sightstalker.models.browser import BrowserContextConfig

_ID = "fp_test_00000001"


def _profile(**kw: object) -> EnvironmentProfile:
    base: dict[str, object] = {"profile_id": _ID, "name": "desktop"}
    base.update(kw)
    return EnvironmentProfile(**base)  # type: ignore[arg-type]


def test_apply_sets_environment_fields_and_provenance() -> None:
    base = BrowserContextConfig()
    profile = _profile(
        user_agent="UA/1.0",
        locale="en-US",
        timezone_id="UTC",
        color_scheme="dark",
        reduced_motion="reduce",
    )
    result = DefaultEnvironmentProfileApplicator().apply(
        base=base, environment=profile
    )
    assert result.user_agent == "UA/1.0"
    assert result.locale == "en-US"
    assert result.timezone_id == "UTC"
    assert result.color_scheme == "dark"
    assert result.reduced_motion == "reduce"
    assert result.environment_profile_id == _ID


def test_apply_does_not_mutate_base() -> None:
    base = BrowserContextConfig()
    DefaultEnvironmentProfileApplicator().apply(
        base=base, environment=_profile(user_agent="UA/1.0")
    )
    assert base.user_agent is None
    assert base.environment_profile_id is None


def test_apply_skips_unset_profile_fields() -> None:
    base = BrowserContextConfig(locale="fr-FR")
    # Profile sets only user_agent; locale should be preserved from base.
    result = DefaultEnvironmentProfileApplicator().apply(
        base=base, environment=_profile(user_agent="UA/1.0")
    )
    assert result.locale == "fr-FR"
    assert result.user_agent == "UA/1.0"


def test_apply_does_not_apply_navigator() -> None:
    base = BrowserContextConfig()
    profile = _profile(navigator=NavigatorProfile(platform="Linux"))
    result = DefaultEnvironmentProfileApplicator().apply(
        base=base, environment=profile
    )
    # Navigator must not leak into context config in any field.
    dumped = result.model_dump()
    assert "navigator" not in dumped
    assert "platform" not in dumped
