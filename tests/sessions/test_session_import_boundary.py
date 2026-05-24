"""Import-boundary tests for sightstalker.sessions (spec 21.7).

The sessions package must stay free of browser-engine, persistence, CLI,
logging, resilience, and web-server dependencies so the lifecycle surface
remains portable and cheaply importable. These tests confirm both that the
package imports without Camoufox installed and that no module pulls in a
prohibited top-level dependency (verified via AST, so mentions in comments or
docstrings are ignored).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import sightstalker.sessions as sessions_pkg

# Top-level module names the sessions package must never import.
_PROHIBITED = {
    "camoufox": "Camoufox",
    "playwright": "Playwright",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "Alembic",
    "typer": "Typer",
    "loguru": "loguru",
    "rich": "rich",
    "tenacity": "tenacity",
    "fastapi": "FastAPI",
    "uvicorn": "Uvicorn",
}


def _session_module_files() -> list[Path]:
    pkg_dir = Path(sessions_pkg.__file__).parent
    return sorted(pkg_dir.glob("*.py"))


def _imported_top_levels(path: Path) -> set[str]:
    """Return the set of top-level module names imported by ``path`` (AST)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Only absolute imports carry a module; ignore relative (level > 0).
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def _all_imported_top_levels() -> set[str]:
    found: set[str] = set()
    for path in _session_module_files():
        found |= _imported_top_levels(path)
    return found


def test_import_sessions_without_camoufox() -> None:
    # Re-importing must not require Camoufox (it is an optional extra).
    module = importlib.import_module("sightstalker.sessions")
    assert module is not None


def test_import_session_manager_symbol() -> None:
    from sightstalker.sessions import SessionManager

    assert SessionManager is not None


@pytest.mark.parametrize("module_name", sorted(_PROHIBITED))
def test_sessions_does_not_import_prohibited(module_name: str) -> None:
    imported = _all_imported_top_levels()
    assert module_name not in imported, (
        f"sessions package must not import {_PROHIBITED[module_name]}"
    )


def test_comment_mentions_do_not_trip_ast_scan() -> None:
    # A module that only *mentions* prohibited names in comments/strings must
    # not be flagged. We synthesize such source and confirm the AST scan is
    # clean, proving the detection is import-based rather than text-based.
    sample = (
        '"""This docstring mentions camoufox, playwright, sqlalchemy, typer."""\n'
        "# loguru and rich and tenacity and fastapi and uvicorn are named here\n"
        "X = 'alembic playwright camoufox'\n"
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
    assert _PROHIBITED.keys() & names == set()
