# pyright: reportPrivateUsage=false
"""Camoufox context-kwargs mapping tests (no browser launch)."""

from __future__ import annotations

import ast
from pathlib import Path

from sightstalker.engines.camoufox import _build_context_kwargs
from sightstalker.models.browser import BrowserContextConfig


def test_maps_user_agent() -> None:
    kwargs = _build_context_kwargs(BrowserContextConfig(user_agent="UA/1.0"))
    assert kwargs["user_agent"] == "UA/1.0"


def test_maps_color_scheme_and_reduced_motion() -> None:
    kwargs = _build_context_kwargs(
        BrowserContextConfig(color_scheme="dark", reduced_motion="reduce")
    )
    assert kwargs["color_scheme"] == "dark"
    assert kwargs["reduced_motion"] == "reduce"


def test_does_not_map_environment_profile_id() -> None:
    kwargs = _build_context_kwargs(
        BrowserContextConfig(environment_profile_id="fp_test_00000001")
    )
    assert "environment_profile_id" not in kwargs
    # The id must not leak under any key/value.
    assert "fp_test_00000001" not in str(kwargs)


def test_unset_new_fields_absent_from_kwargs() -> None:
    kwargs = _build_context_kwargs(BrowserContextConfig())
    for key in ("user_agent", "color_scheme", "reduced_motion"):
        assert key not in kwargs


def test_existing_mapping_preserved() -> None:
    kwargs = _build_context_kwargs(
        BrowserContextConfig(locale="en-US", timezone_id="UTC")
    )
    assert kwargs["locale"] == "en-US"
    assert kwargs["timezone_id"] == "UTC"


def test_viewport_subfields_not_mapped() -> None:
    # device_scale_factor/is_mobile/has_touch native mapping deferred.
    from sightstalker.models.browser import ViewportConfig

    config = BrowserContextConfig(
        viewport=ViewportConfig(
            width=1280, height=720, device_scale_factor=2.0,
            is_mobile=True, has_touch=True,
        )
    )
    kwargs = _build_context_kwargs(config)
    viewport = kwargs.get("viewport")
    assert viewport == {"width": 1280, "height": 720}
    assert "device_scale_factor" not in str(kwargs)
    assert "is_mobile" not in str(kwargs)
    assert "has_touch" not in str(kwargs)


def test_build_context_kwargs_does_not_reference_environment_types() -> None:
    # Source-shape: adapter mapping is data-only.
    import sightstalker.engines.camoufox as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    func: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_context_kwargs":
            func = node
            break
    assert func is not None
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    for forbidden in (
        "EnvironmentProfile",
        "NavigatorProfile",
        "EnvironmentProfileStore",
        "ContextConfigResolver",
    ):
        assert forbidden not in names
