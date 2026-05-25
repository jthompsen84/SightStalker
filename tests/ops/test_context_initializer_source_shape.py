"""Source-shape tests for the initializer module and ops.runs wiring region.

Uses AST (not raw substring scanning) to prove package-provided initializer-chain
code and the new wiring region in ``ops.runs`` introduce no executable calls to
forbidden browser/page/native/persistence methods, and that the initializer
module imports only allowed modules. These checks apply to package code only;
they do not sandbox caller-supplied trusted initializers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import sightstalker.ops as ops_pkg

_OPS_DIR = Path(ops_pkg.__file__).parent
_INITIALIZERS = _OPS_DIR / "initializers.py"
_RUNS = _OPS_DIR / "runs.py"

# Forbidden executable call attribute names (call sites only).
_FORBIDDEN_CALLS = {
    "new_page",
    "goto",
    "screenshot",
    "storage_state",
    "start_tracing",
    "stop_tracing",
    "add_init_script",
    "evaluate",
    "evaluate_on_new_document",
}
# Forbidden native attribute access.
_FORBIDDEN_ATTRS = {"native_context", "native_page", "native_browser"}
# Forbidden constructed/referenced names.
_FORBIDDEN_NAMES = {
    "ArtifactRepository",
    "RunRepository",
    "SessionRepository",
    "ArtifactManager",
    "DiagnosticArtifactRecorder",
}


def _called_attrs(node: ast.AST) -> set[str]:
    """Attribute names that appear as the function of a call: x.y(...)."""
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            found.add(n.func.attr)
    return found


def _accessed_attrs(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute):
            found.add(n.attr)
    return found


def _referenced_names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            found.add(n.id)
    return found


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                mods.add(node.module)
    return mods


def test_initializers_module_no_forbidden_calls() -> None:
    tree = ast.parse(_INITIALIZERS.read_text(encoding="utf-8"))
    assert _called_attrs(tree) & _FORBIDDEN_CALLS == set()
    assert _accessed_attrs(tree) & _FORBIDDEN_ATTRS == set()
    assert _referenced_names(tree) & _FORBIDDEN_NAMES == set()


def test_initializers_module_allowed_imports_only() -> None:
    mods = _imported_modules(_INITIALIZERS.read_text(encoding="utf-8"))
    forbidden = {
        "sightstalker.engines.camoufox",
        "camoufox",
        "playwright",
        "sightstalker.cli",
        "sightstalker.persistence",
        "sightstalker.interaction",
        "sightstalker.environment.stores",
        "sightstalker.environment.selectors",
        "sightstalker.environment.applicators",
    }
    for mod in mods:
        assert mod not in forbidden, f"forbidden import in initializers: {mod}"
        assert not mod.startswith("sightstalker.interaction")


def _wiring_region(source: str) -> ast.AST:
    """Extract the initializer-scope builder + the executor function nodes."""
    tree = ast.parse(source)
    nodes: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            "_build_context_initialization_scope",
            "execute_managed_run",
        ):
            nodes.append(node)
    assert nodes, "wiring region functions not found"
    module = ast.Module(body=nodes, type_ignores=[])
    return module


def test_wiring_region_no_forbidden_browser_calls() -> None:
    region = _wiring_region(_RUNS.read_text(encoding="utf-8"))
    called = _called_attrs(region)
    # The executor legitimately calls plan/new_page via the *plan*, but the
    # wiring region itself must not directly call these page/context methods.
    # new_page is invoked by RunSurface/plan, not by the wiring region directly;
    # assert the forbidden direct browser-mutation calls are absent.
    for forbidden in ("goto", "screenshot", "storage_state", "start_tracing",
                      "stop_tracing", "add_init_script", "evaluate",
                      "evaluate_on_new_document"):
        assert forbidden not in called, f"wiring region calls {forbidden}"


def test_wiring_region_no_native_access() -> None:
    region = _wiring_region(_RUNS.read_text(encoding="utf-8"))
    assert _accessed_attrs(region) & _FORBIDDEN_ATTRS == set()


def test_selftest_detects_forbidden_call() -> None:
    src = "async def f(x):\n    await x.add_init_script('y')\n"
    tree = ast.parse(src)
    assert "add_init_script" in _called_attrs(tree)


def test_selftest_detects_native_attr() -> None:
    src = "def f(x):\n    return x.native_context\n"
    tree = ast.parse(src)
    assert "native_context" in _accessed_attrs(tree)
