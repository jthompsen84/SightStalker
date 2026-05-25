"""Import-boundary tests for the resilience package.

Two layers of enforcement:
1. Recursive AST scans over ``resilience/*`` forbid disallowed top-level imports
   (camoufox, playwright, fastapi, uvicorn, engines, cli.main/app) and confine
   any ``sqlalchemy`` import to ``classification.py``.
2. Fresh-subprocess ``sys.modules`` checks confirm that importing non-resilience
   modules never loads loguru/tenacity, and that importing the CLI loads
   resilience without configuring a loguru sink.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import sightstalker.resilience as resilience_pkg

_RESILIENCE_DIR = Path(resilience_pkg.__file__).parent

_FORBIDDEN_ROOTS = {
    "camoufox",
    "playwright",
    "fastapi",
    "uvicorn",
}
_FORBIDDEN_DOTTED = {
    "sightstalker.engines",
    "sightstalker.engines.camoufox",
    "sightstalker.cli.main",
    "sightstalker.cli.app",
}


def _py_files() -> list[Path]:
    return sorted(_RESILIENCE_DIR.rglob("*.py"))


def _imports(path: Path) -> tuple[set[str], set[str]]:
    """Return (root_names, dotted_names) imported anywhere in the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    dotted: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
                dotted.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                roots.add(node.module.split(".")[0])
                dotted.add(node.module)
    return roots, dotted


def test_no_forbidden_imports_in_resilience() -> None:
    offenders: dict[str, set[str]] = {}
    for path in _py_files():
        roots, dotted = _imports(path)
        bad = (roots & _FORBIDDEN_ROOTS) | (dotted & _FORBIDDEN_DOTTED)
        # Any dotted name that *starts with* a forbidden engine/cli path.
        for name in dotted:
            if name.startswith("sightstalker.engines") or name in _FORBIDDEN_DOTTED:
                bad.add(name)
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"forbidden imports in resilience: {offenders}"


def test_sqlalchemy_confined_to_classification() -> None:
    for path in _py_files():
        roots, _ = _imports(path)
        if "sqlalchemy" in roots:
            assert path.name == "classification.py", (
                f"sqlalchemy imported outside classification.py: {path.name}"
            )


def test_scan_is_nonempty() -> None:
    assert len(_py_files()) >= 8


def _probe(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_non_resilience_modules_do_not_load_loguru_or_tenacity() -> None:
    for mod in (
        "sightstalker",
        "sightstalker.models",
        "sightstalker.artifacts",
        "sightstalker.sessions",
        "sightstalker.persistence",
        "sightstalker.diagnostics",
        "sightstalker.engines.base",
    ):
        code = (
            f"import sys, {mod};"
            "bad=[m for m in ('loguru','tenacity') if m in sys.modules];"
            "print(','.join(bad));"
            "sys.exit(1 if bad else 0)"
        )
        result = _probe(code)
        assert result.returncode == 0, f"{mod}: {result.stdout}{result.stderr}"


def test_importing_resilience_does_not_configure_loguru() -> None:
    code = (
        "import sys, sightstalker.resilience;"
        "print('loguru' in sys.modules);"
        "sys.exit(1 if 'loguru' in sys.modules else 0)"
    )
    result = _probe(code)
    assert result.returncode == 0, result.stdout + result.stderr


def test_importing_cli_loads_resilience_without_loguru_sink() -> None:
    code = (
        "import sys, sightstalker.cli.main;"
        "assert 'sightstalker.resilience' in sys.modules, 'resilience not loaded';"
        "loaded = 'loguru' in sys.modules;"
        "print('loguru_loaded=' + str(loaded));"
        "sys.exit(1 if loaded else 0)"
    )
    result = _probe(code)
    assert result.returncode == 0, result.stdout + result.stderr
