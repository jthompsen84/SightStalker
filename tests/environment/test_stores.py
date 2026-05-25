"""Store behavior tests."""

from __future__ import annotations

import pytest

from sightstalker.environment.errors import EnvironmentProfileNotFound
from sightstalker.environment.models import EnvironmentProfile
from sightstalker.environment.stores import (
    InMemoryEnvironmentProfileStore,
    NullEnvironmentProfileStore,
)
from sightstalker.resilience import classify_exception

_ID = "fp_test_00000001"


def _profile() -> EnvironmentProfile:
    return EnvironmentProfile(profile_id=_ID, name="desktop")


async def test_in_memory_store_loads_profile() -> None:
    store = InMemoryEnvironmentProfileStore([_profile()])
    loaded = await store.load(_ID)
    assert loaded.profile_id == _ID


async def test_in_memory_store_unknown_raises_not_found() -> None:
    store = InMemoryEnvironmentProfileStore()
    with pytest.raises(EnvironmentProfileNotFound):
        await store.load("fp_test_99999999")


async def test_unknown_profile_classifies_as_usage_error() -> None:
    store = InMemoryEnvironmentProfileStore()
    try:
        await store.load("fp_test_99999999")
    except EnvironmentProfileNotFound as exc:
        operator = classify_exception(exc)
        assert operator.type == "UsageError"
        assert operator.exit_code == 2
        assert "fp_test_99999999" not in operator.message
    else:
        raise AssertionError("expected EnvironmentProfileNotFound")


async def test_null_store_always_not_found() -> None:
    store = NullEnvironmentProfileStore()
    with pytest.raises(EnvironmentProfileNotFound):
        await store.load(_ID)


async def test_add_then_load() -> None:
    store = InMemoryEnvironmentProfileStore()
    store.add(_profile())
    assert (await store.load(_ID)).name == "desktop"


def test_store_module_does_no_file_io() -> None:
    # Source-shape: stores.py must not import file/persistence modules.
    import ast
    from pathlib import Path

    import sightstalker.environment.stores as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for forbidden in ("pathlib", "io", "sightstalker.persistence"):
        assert not any(
            m == forbidden or m.startswith(forbidden + ".") for m in imported
        ), f"stores.py must not import {forbidden}"
