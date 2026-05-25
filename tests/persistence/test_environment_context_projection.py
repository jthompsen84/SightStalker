# pyright: reportPrivateUsage=false
"""Persistence projection/rehydration tests for new context fields."""

from __future__ import annotations

from sightstalker.models.browser import BrowserContextConfig, BrowserLaunchConfig
from sightstalker.models.sessions import SessionConfig
from sightstalker.persistence.serialization import (
    _session_config_from_projection,
    persistable_session_config,
)


def _config(**ctx: object) -> SessionConfig:
    return SessionConfig(
        launch=BrowserLaunchConfig(),
        context=BrowserContextConfig(**ctx),  # type: ignore[arg-type]
    )


def test_round_trip_identity_all_four_fields() -> None:
    cfg = _config(
        user_agent="UA/1.0",
        color_scheme="dark",
        reduced_motion="reduce",
        environment_profile_id="fp_test_00000001",
    )
    projection = persistable_session_config(cfg)
    rehydrated = _session_config_from_projection(projection)
    assert rehydrated.context.user_agent == "UA/1.0"
    assert rehydrated.context.color_scheme == "dark"
    assert rehydrated.context.reduced_motion == "reduce"
    assert rehydrated.context.environment_profile_id == "fp_test_00000001"


def test_missing_fields_rehydrate_as_none() -> None:
    projection = persistable_session_config(_config())
    # Simulate an older stored projection lacking the new keys.
    for key in (
        "user_agent",
        "color_scheme",
        "reduced_motion",
        "environment_profile_id",
    ):
        projection["context"].pop(key, None)  # type: ignore[union-attr]
    rehydrated = _session_config_from_projection(projection)
    assert rehydrated.context.user_agent is None
    assert rehydrated.context.color_scheme is None
    assert rehydrated.context.reduced_motion is None
    assert rehydrated.context.environment_profile_id is None


def test_unknown_context_keys_ignored() -> None:
    projection = persistable_session_config(_config(user_agent="UA/1.0"))
    projection["context"]["totally_unknown_key"] = "x"  # type: ignore[index]
    rehydrated = _session_config_from_projection(projection)
    assert rehydrated.context.user_agent == "UA/1.0"


def test_projection_does_not_store_profile_objects() -> None:
    projection = persistable_session_config(
        _config(environment_profile_id="fp_test_00000001")
    )
    blob = str(projection)
    # Only the id string is stored; no EnvironmentProfile/NavigatorProfile/
    # resolution objects.
    assert "EnvironmentProfile" not in blob
    assert "NavigatorProfile" not in blob
    assert "ContextConfigResolution" not in blob
    assert "applied_environment_fields" not in blob


def test_projection_is_json_safe() -> None:
    import json

    projection = persistable_session_config(
        _config(
            user_agent="UA/1.0",
            color_scheme="light",
            reduced_motion="no-preference",
            environment_profile_id="fp_test_00000001",
        )
    )
    assert json.loads(json.dumps(projection)) == projection


def test_invalid_stored_color_scheme_falls_back_to_none() -> None:
    projection = persistable_session_config(_config(color_scheme="dark"))
    projection["context"]["color_scheme"] = "neon"  # type: ignore[index]
    rehydrated = _session_config_from_projection(projection)
    assert rehydrated.context.color_scheme is None
