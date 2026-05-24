"""Import-boundary tests for sightstalker.artifacts (spec 17, 19).

The artifacts package must depend only on the standard library, Pydantic,
sightstalker.models, and the neutral sightstalker.ids module. It must never
import a browser engine, persistence, CLI, logging, resilience, or web library,
and must never import sightstalker.sessions (which would invert the dependency
and create a cycle). Detection is AST-based so comment/docstring mentions of
prohibited names do not trip the scan.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import sightstalker.artifacts as artifacts_pkg

_PROHIBITED = {
    "camoufox": "Camoufox",
    "playwright": "Playwright",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "Alembic",
    "typer": "Typer",
    "rich": "rich",
    "loguru": "loguru",
    "tenacity": "tenacity",
    "fastapi": "FastAPI",
    "uvicorn": "Uvicorn",
}


def _module_files() -> list[Path]:
    pkg_dir = Path(artifacts_pkg.__file__).parent
    return sorted(pkg_dir.glob("*.py"))


def _imported_top_levels(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def _imported_dotted(path: Path) -> set[str]:
    """Return fully-dotted absolute import targets (for sightstalker.* checks)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module)
    return names


def _all_top_levels() -> set[str]:
    found: set[str] = set()
    for path in _module_files():
        found |= _imported_top_levels(path)
    return found


def _all_dotted() -> set[str]:
    found: set[str] = set()
    for path in _module_files():
        found |= _imported_dotted(path)
    return found


def test_import_artifacts_without_camoufox() -> None:
    module = importlib.import_module("sightstalker.artifacts")
    assert module is not None


def test_import_artifact_manager_symbol() -> None:
    from sightstalker.artifacts import ArtifactManager

    assert ArtifactManager is not None


@pytest.mark.parametrize("module_name", sorted(_PROHIBITED))
def test_artifacts_does_not_import_prohibited(module_name: str) -> None:
    assert module_name not in _all_top_levels(), (
        f"artifacts must not import {_PROHIBITED[module_name]}"
    )


def test_artifacts_does_not_import_sessions() -> None:
    dotted = _all_dotted()
    for name in dotted:
        assert not name.startswith("sightstalker.sessions"), (
            "artifacts must not import sightstalker.sessions"
        )


def test_artifacts_only_uses_allowed_sightstalker_modules() -> None:
    dotted = _all_dotted()
    sightstalker_imports = {n for n in dotted if n.startswith("sightstalker")}
    allowed_prefixes = ("sightstalker.models", "sightstalker.ids", "sightstalker.artifacts")
    for name in sightstalker_imports:
        assert name.startswith(allowed_prefixes), (
            f"artifacts imported unexpected internal module: {name}"
        )


def test_comment_mentions_do_not_trip_scan() -> None:
    sample = (
        '"""Mentions camoufox, playwright, sqlalchemy and sightstalker.sessions."""\n'
        "# typer rich loguru tenacity fastapi uvicorn alembic\n"
        "S = 'sightstalker.sessions camoufox'\n"
        "import json\n"
    )
    tree = ast.parse(sample)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    assert names == {"json"}
