"""
Import-boundary tests for CAMOUFOX-ENGINE-1.

These tests enforce the architectural rule that Camoufox/Playwright may only
be imported inside src/sightstalker/engines/camoufox.py, and only lazily, so
that the rest of the package imports without the browser package or binary.
"""

from __future__ import annotations

import ast
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the production source tree
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "sightstalker"
_ADAPTER_FILE = _SRC_ROOT / "engines" / "camoufox.py"


# ---------------------------------------------------------------------------
# 1–4. Imports that must work without camoufox installed / browser fetched
# ---------------------------------------------------------------------------


def test_import_sightstalker() -> None:
    import sightstalker

    assert sightstalker.__version__ == "0.4.5"


def test_import_models() -> None:
    import sightstalker.models as _models

    assert _models is not None


def test_import_engines_base() -> None:
    import sightstalker.engines.base as _base

    assert _base is not None


def test_import_camoufox_engine_symbol() -> None:
    from sightstalker.engines import CamoufoxEngine

    assert CamoufoxEngine is not None


# ---------------------------------------------------------------------------
# 5–6. Source-shape scan: camoufox/playwright imports confined to adapter
# ---------------------------------------------------------------------------


def _iter_production_py_files() -> list[Path]:
    return sorted(p for p in _SRC_ROOT.rglob("*.py"))


def _module_level_imports(path: Path) -> set[str]:
    """
    Return the set of top-level (module-scope) imported root package names.

    Only module-level imports count as boundary violations; lazy imports
    inside functions are permitted in the adapter.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in tree.body:  # module-level statements only
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def test_no_module_level_browser_import_anywhere() -> None:
    """No production file may import camoufox/playwright at module scope."""
    offenders: dict[str, set[str]] = {}
    for path in _iter_production_py_files():
        roots = _module_level_imports(path)
        bad = roots & {"camoufox", "playwright"}
        if bad:
            offenders[str(path.relative_to(_REPO_ROOT))] = bad
    assert not offenders, f"Module-level browser imports found: {offenders}"


def test_camoufox_import_only_in_adapter_file() -> None:
    """
    Any reference to camoufox/playwright imports (even lazy) must appear only
    in engines/camoufox.py across the production tree.
    """
    offenders: list[str] = []
    for path in _iter_production_py_files():
        if path == _ADAPTER_FILE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"camoufox", "playwright"}:
                        offenders.append(str(path.relative_to(_REPO_ROOT)))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in {
                    "camoufox",
                    "playwright",
                }:
                    offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, f"Browser imports outside adapter: {offenders}"


def test_adapter_does_not_import_playwright_at_all() -> None:
    """Preferred: the adapter wraps Playwright-compatible objects structurally."""
    tree = ast.parse(_ADAPTER_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (
                node.module and node.module.split(".")[0] == "playwright"
            ), "Adapter should not import playwright directly"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "playwright"


def test_adapter_camoufox_import_is_lazy() -> None:
    """The adapter must not import camoufox at module scope."""
    roots = _module_level_imports(_ADAPTER_FILE)
    assert "camoufox" not in roots


# ---------------------------------------------------------------------------
# 7–8. Construction without browser launch / binary fetch
# ---------------------------------------------------------------------------


def test_engine_constructs_without_browser_launch() -> None:
    from sightstalker.engines import CamoufoxEngine

    engine = CamoufoxEngine()
    assert engine.name == "camoufox"


def test_engine_constructs_without_browser_binary() -> None:
    # No call to launch(), so no AsyncCamoufox import or binary fetch occurs.
    from sightstalker.engines import CamoufoxEngine

    engine = CamoufoxEngine(async_camoufox_factory=None)
    assert engine is not None
