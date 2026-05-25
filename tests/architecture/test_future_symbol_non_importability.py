"""Guard: still-future names remain documentation-only / non-public.

``ENVIRONMENT-1`` implements the environment names (``EnvironmentProfile``,
``ContextConfigResolver``, ``ContextConfigResolution``, etc.) and
``CONTEXT-INITIALIZER-1`` implements ``ContextInitializer`` /
``ContextInitializerChain`` / ``ContextInitializationScope`` in
``sightstalker.ops``, so those are no longer in the forbidden set. The
interaction names remain future and non-importable, and ``FingerprintProfile``
must remain a non-exported internal alias.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import sightstalker

# Names that must still NOT be importable production symbols in v0.4.5.
_STILL_FUTURE_NAMES = [
    "InteractionProfile",
    "InteractionActivation",
    "InteractionSimulator",
    "TimingStrategy",
    "MouseMovementStrategy",
    "InteractionStrategy",
    "PageInteractionTarget",
]


def _all_existing_modules() -> list[str]:
    names = ["sightstalker"]
    for info in pkgutil.walk_packages(sightstalker.__path__, "sightstalker."):
        names.append(info.name)
    return names


def test_still_future_names_absent_from_every_module() -> None:
    """SNAPSHOT-v0.4.3: interaction/context-initializer names remain future."""
    offenders: dict[str, list[str]] = {}
    for modname in _all_existing_modules():
        try:
            module = importlib.import_module(modname)
        except Exception:
            continue
        present = [n for n in _STILL_FUTURE_NAMES if hasattr(module, n)]
        if present:
            offenders[modname] = present
    assert offenders == {}, f"future symbols are importable: {offenders}"


def test_interaction_dotted_modules_not_importable() -> None:
    """SNAPSHOT-v0.4.3: relaxed by INTERACTION-1."""
    for dotted in (
        "sightstalker.interaction",
        "sightstalker.interaction.simulator",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(dotted)


def test_environment_names_now_importable() -> None:
    """ENVIRONMENT-1: environment names are now public symbols."""
    from sightstalker.environment import (
        ContextConfigResolution,
        ContextConfigResolver,
        DefaultContextConfigResolver,
        EnvironmentProfile,
        NavigatorProfile,
    )

    for symbol in (
        ContextConfigResolution,
        ContextConfigResolver,
        DefaultContextConfigResolver,
        EnvironmentProfile,
        NavigatorProfile,
    ):
        assert symbol is not None


def test_context_initializer_names_now_importable() -> None:
    """CONTEXT-INITIALIZER-1: initializer seam names are now public from ops."""
    from sightstalker.ops import (
        ContextInitializationScope,
        ContextInitializer,
        ContextInitializerChain,
    )

    for symbol in (
        ContextInitializationScope,
        ContextInitializer,
        ContextInitializerChain,
    ):
        assert symbol is not None


def test_fingerprint_profile_not_publicly_exported() -> None:
    """FingerprintProfile remains an internal, non-exported alias."""
    import sightstalker.environment as env

    assert "FingerprintProfile" not in env.__all__
    assert not hasattr(env, "FingerprintProfile")


def test_accepted_fingerprint_profile_id_still_present() -> None:
    """The accepted id type must remain importable (legacy naming debt)."""
    from sightstalker.models import FingerprintProfileId

    assert FingerprintProfileId is not None
