"""Validation and repr tests for environment models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sightstalker.environment.models import (
    ContextConfigOverrides,
    EnvironmentProfile,
    FingerprintProfile,
    NavigatorProfile,
)

_VALID_ID = "fp_test_00000001"


def _profile(**kw: object) -> EnvironmentProfile:
    base: dict[str, object] = {"profile_id": _VALID_ID, "name": "desktop"}
    base.update(kw)
    return EnvironmentProfile(**base)  # type: ignore[arg-type]


def test_minimal_profile_valid() -> None:
    profile = _profile()
    assert profile.profile_id == _VALID_ID
    assert profile.schema_version == "environment_profile_v1"


def test_name_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        _profile(name="   ")


def test_user_agent_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        _profile(user_agent="   ")


def test_user_agent_rejects_control_chars() -> None:
    with pytest.raises(ValidationError):
        _profile(user_agent="Mozilla\x00/5.0")
    with pytest.raises(ValidationError):
        _profile(user_agent="line\nbreak")


def test_user_agent_repr_suppressed() -> None:
    profile = _profile(user_agent="Mozilla/5.0 SecretAgent")
    assert "SecretAgent" not in repr(profile)


def test_locale_and_timezone_validation() -> None:
    with pytest.raises(ValidationError):
        _profile(locale="  ")
    with pytest.raises(ValidationError):
        _profile(timezone_id="bad\x01tz")


def test_schema_version_pinned() -> None:
    with pytest.raises(ValidationError):
        _profile(schema_version="environment_profile_v2")


def test_color_scheme_and_reduced_motion_literals() -> None:
    profile = _profile(color_scheme="dark", reduced_motion="reduce")
    assert profile.color_scheme == "dark"
    assert profile.reduced_motion == "reduce"
    with pytest.raises(ValidationError):
        _profile(color_scheme="neon")


def test_profile_is_frozen() -> None:
    profile = _profile()
    with pytest.raises(ValidationError):
        profile.name = "other"  # type: ignore[misc]


def test_internal_alias_is_environment_profile() -> None:
    assert FingerprintProfile is EnvironmentProfile


def test_navigator_languages_reject_empty_entry() -> None:
    with pytest.raises(ValidationError):
        NavigatorProfile(languages=("en", "  "))


def test_navigator_has_no_extra_field() -> None:
    # NavigatorProfile.extra was intentionally omitted in ENVIRONMENT-1.
    assert "extra" not in NavigatorProfile.model_fields
    with pytest.raises(ValidationError):
        NavigatorProfile(extra={"x": 1})  # type: ignore[call-arg]


def test_context_overrides_user_agent_validation_matches() -> None:
    with pytest.raises(ValidationError):
        ContextConfigOverrides(user_agent="  ")
    with pytest.raises(ValidationError):
        ContextConfigOverrides(user_agent="bad\x00ua")
    ok = ContextConfigOverrides(user_agent="Mozilla/5.0")
    assert "Mozilla" not in repr(ok)
