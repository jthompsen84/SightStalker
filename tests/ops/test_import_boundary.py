"""Import-boundary and source-shape tests for the ops boundary.

1. Recursive AST scan over ``src/sightstalker/ops/**`` forbids importing CLI
   command/rendering modules, Typer/Rich, the Camoufox adapter, Playwright, and
   the interaction/environment packages.
2. Source-shape scan asserts ``cli/runs.py`` no longer *defines* the moved
   primitives.
3. Production import scan asserts no production module imports the moved
   primitives from ``sightstalker.cli.runs``.
4. Fresh-subprocess check confirms ``import sightstalker.ops`` does not load the
   Camoufox adapter or Playwright.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import sightstalker.cli as cli_pkg
import sightstalker.ops as ops_pkg

_OPS_DIR = Path(ops_pkg.__file__).parent
_CLI_DIR = Path(cli_pkg.__file__).parent
_SRC_DIR = _CLI_DIR.parent  # src/sightstalker

_FORBIDDEN_OPS_DOTTED = {
    "sightstalker.cli.app",
    "sightstalker.cli.main",
    "sightstalker.cli.output",
    "sightstalker.cli.config",
    "sightstalker.cli.context",
    "sightstalker.cli.types",
    "sightstalker.cli.errors",
    "sightstalker.cli.redaction",
    "sightstalker.engines.camoufox",
    "sightstalker.interaction",
    "sightstalker.environment.stores",
    "sightstalker.environment.selectors",
    "sightstalker.environment.applicators",
    "sightstalker.environment.resolver",
    "sightstalker.environment.errors",
}
_FORBIDDEN_OPS_ROOTS = {"typer", "rich", "camoufox", "playwright"}

# After ENVIRONMENT-1, ops may import only these environment modules.
_ALLOWED_OPS_ENV_MODULES = {
    "sightstalker.environment.protocols",
    "sightstalker.environment.models",
    "sightstalker.environment.types",
}

_MOVED_SYMBOLS = {
    "RunSurface",
    "PlanResult",
    "Plan",
    "EngineFactory",
    "_apply_mode_override",
    "_build_request",
    "_persist_run",
    "execute_managed_run",
}


def _module_imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    dotted: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
                dotted.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                roots.add(node.module.split(".")[0])
                dotted.add(node.module)
    return roots, dotted


def test_ops_has_no_forbidden_imports() -> None:
    offenders: dict[str, set[str]] = {}
    for path in sorted(_OPS_DIR.rglob("*.py")):
        roots, dotted = _module_imports(path)
        bad = (roots & _FORBIDDEN_OPS_ROOTS) | (dotted & _FORBIDDEN_OPS_DOTTED)
        for name in dotted:
            if name.startswith("sightstalker.engines.camoufox"):
                bad.add(name)
            if name.startswith("sightstalker.interaction"):
                bad.add(name)
            # Environment is allowed only via the narrow protocol/model modules.
            if name.startswith("sightstalker.environment") and (
                name not in _ALLOWED_OPS_ENV_MODULES
            ):
                bad.add(name)
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"forbidden imports in ops: {offenders}"


def test_ops_scan_nonempty() -> None:
    assert len(list(_OPS_DIR.rglob("*.py"))) >= 5


def test_cli_runs_does_not_define_moved_symbols() -> None:
    runs_path = _CLI_DIR / "runs.py"
    tree = ast.parse(runs_path.read_text(encoding="utf-8"), filename=str(runs_path))
    defined: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
    leaked = defined & _MOVED_SYMBOLS
    assert leaked == set(), f"cli.runs still defines moved symbols: {leaked}"


def test_no_production_module_imports_moved_primitives_from_cli_runs() -> None:
    offenders: dict[str, set[str]] = {}
    for path in sorted(_SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "sightstalker.cli.runs":
                names = {alias.name for alias in node.names}
                bad = names & _MOVED_SYMBOLS
                if bad:
                    offenders[str(path.relative_to(_SRC_DIR))] = bad
    assert offenders == {}, f"moved primitives imported from cli.runs: {offenders}"


def test_importing_ops_subprocess_no_browser_adapter() -> None:
    probe = (
        "import sys, sightstalker.ops;"
        "bad=[m for m in ('camoufox','playwright','sightstalker.engines.camoufox')"
        " if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
