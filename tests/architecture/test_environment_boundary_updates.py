"""Verify v0.4.3 boundary guards are correctly updated for ENVIRONMENT-1.

Environment now exists; interaction remains absent; permanent boundaries
(engines/sessions/cli/persistence must not import environment) still hold.
"""

from __future__ import annotations

import ast
from pathlib import Path

import sightstalker

_PKG_ROOT = Path(sightstalker.__file__).resolve().parent


def _imports_under(pkg: str) -> dict[str, set[str]]:
    base = _PKG_ROOT / pkg
    result: dict[str, set[str]] = {}
    for path in sorted(base.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        mods: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.add(node.module)
        result[path.name] = mods
    return result


def _imports_environment(mods: set[str]) -> bool:
    return any(
        m == "sightstalker.environment" or m.startswith("sightstalker.environment.")
        for m in mods
    )


def test_environment_package_present() -> None:
    assert (_PKG_ROOT / "environment").is_dir()


def test_interaction_package_absent() -> None:
    assert not (_PKG_ROOT / "interaction").exists()


def test_engines_do_not_import_environment_permanent() -> None:
    for name, mods in _imports_under("engines").items():
        assert not _imports_environment(mods), f"{name} imports environment"


def test_sessions_do_not_import_environment_permanent() -> None:
    for name, mods in _imports_under("sessions").items():
        assert not _imports_environment(mods), f"{name} imports environment"


def test_cli_does_not_import_environment_permanent() -> None:
    for name, mods in _imports_under("cli").items():
        assert not _imports_environment(mods), f"{name} imports environment"


def test_persistence_does_not_import_environment_permanent() -> None:
    for name, mods in _imports_under("persistence").items():
        assert not _imports_environment(mods), f"{name} imports environment"


def test_ops_imports_only_narrow_environment_modules() -> None:
    allowed = {
        "sightstalker.environment.protocols",
        "sightstalker.environment.models",
        "sightstalker.environment.types",
    }
    for name, mods in _imports_under("ops").items():
        for mod in mods:
            if mod.startswith("sightstalker.environment"):
                assert mod in allowed, f"{name} imports disallowed env module {mod}"


def test_behavior_boundary_doc_marks_environment_implemented() -> None:
    doc = (
        _PKG_ROOT.parents[1]
        / "docs"
        / "architecture"
        / "behavior-boundary.md"
    )
    text = doc.read_text(encoding="utf-8")
    assert "ENVIRONMENT-1" in text
    # Interaction still future.
    assert "INTERACTION-1" in text
