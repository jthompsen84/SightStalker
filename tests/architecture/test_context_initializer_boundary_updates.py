"""Architecture boundary updates for CONTEXT-INITIALIZER-1.

Asserts: ContextInitializer seam is implemented in ops; the interaction package
remains absent; permanent boundaries hold (engines/sessions/persistence/
environment do not import ops.initializers; CLI does not import/construct it);
and the behavior-boundary doc + README reflect the seam implemented with no
concrete initializer behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path

import sightstalker

_PKG_ROOT = Path(sightstalker.__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parents[1]
_DOC = _REPO_ROOT / "docs" / "architecture" / "behavior-boundary.md"
_README = _REPO_ROOT / "README.md"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                mods.add(node.module)
    return mods


def _py_files(*parts: str) -> list[Path]:
    base = _PKG_ROOT.joinpath(*parts)
    return sorted(base.rglob("*.py")) if base.exists() else []


def test_initializer_seam_implemented_in_ops() -> None:
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
    assert (_PKG_ROOT / "ops" / "initializers.py").is_file()


def test_interaction_package_still_absent() -> None:
    assert not (_PKG_ROOT / "interaction").exists()


def test_engines_do_not_import_ops_initializers() -> None:
    for path in _py_files("engines"):
        mods = _imported_modules(path)
        assert "sightstalker.ops.initializers" not in mods
        assert "sightstalker.ops" not in mods


def test_sessions_do_not_import_ops_initializers() -> None:
    for path in _py_files("sessions"):
        mods = _imported_modules(path)
        assert "sightstalker.ops.initializers" not in mods


def test_environment_does_not_import_ops_initializers() -> None:
    for path in _py_files("environment"):
        mods = _imported_modules(path)
        assert "sightstalker.ops.initializers" not in mods


def test_persistence_does_not_import_ops_initializers() -> None:
    for path in _py_files("persistence"):
        mods = _imported_modules(path)
        assert "sightstalker.ops.initializers" not in mods


def test_cli_does_not_import_ops_initializers() -> None:
    for path in _py_files("cli"):
        mods = _imported_modules(path)
        assert "sightstalker.ops.initializers" not in mods


def _normalize_md(path: Path) -> str:
    lines = [line.lstrip("> ").rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
    return " ".join(" ".join(lines).split())


def test_doc_status_matrix_reflects_initializer_implemented() -> None:
    text = _normalize_md(_DOC)
    assert "CONTEXT-INITIALIZER-1" in text
    assert "trusted" in text.lower()
    # Concrete behavior remains future / not implemented.
    assert "no package-provided concrete initializer" in text.lower() or (
        "ships no package-provided concrete initializer" in text.lower()
    )


def test_readme_states_seam_without_concrete_behavior() -> None:
    text = _normalize_md(_README).lower()
    assert "v0.4.5" in text
    assert "initializer" in text
    # No positive claims of navigator/script injection or sandboxing.
    assert "sandboxed initializer" not in text
