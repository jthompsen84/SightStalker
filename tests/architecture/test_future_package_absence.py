"""Guard: the interaction package remains absent.

``ENVIRONMENT-1`` implements ``sightstalker.environment``, so the v0.4.3
environment-absence snapshot is relaxed here. ``sightstalker.interaction``
remains absent (SNAPSHOT-v0.4.3, relaxed later by ``INTERACTION-1``).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import sightstalker

_PKG_ROOT = Path(sightstalker.__file__).resolve().parent


def test_environment_package_now_present() -> None:
    """ENVIRONMENT-1: environment package is now implemented and importable."""
    assert (_PKG_ROOT / "environment").is_dir()
    module = importlib.import_module("sightstalker.environment")
    assert module is not None


def test_interaction_package_absent() -> None:
    """SNAPSHOT-v0.4.3: relaxed by INTERACTION-1."""
    assert not (_PKG_ROOT / "interaction").exists()


def test_interaction_package_not_importable() -> None:
    """SNAPSHOT-v0.4.3: relaxed by INTERACTION-1."""
    try:
        importlib.import_module("sightstalker.interaction")
    except ModuleNotFoundError:
        return
    raise AssertionError("sightstalker.interaction should not be importable")
