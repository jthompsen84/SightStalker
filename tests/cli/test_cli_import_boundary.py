"""Import-boundary tests for the CLI package.

Importing the CLI must not load any browser package/adapter or web framework.
The concrete Camoufox engine may only be referenced lazily inside the runtime
factory function body.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_SRC_CLI = Path(__file__).resolve().parents[2] / "src" / "sightstalker" / "cli"

_FORBIDDEN_TOP_LEVEL = {
    "camoufox",
    "playwright",
    "fastapi",
    "uvicorn",
    "tenacity",
    "loguru",
}


def _cli_py_files() -> list[Path]:
    return sorted(p for p in _SRC_CLI.rglob("*.py"))


def _module_level_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def test_no_forbidden_top_level_imports_in_cli() -> None:
    offenders: dict[str, set[str]] = {}
    for path in _cli_py_files():
        bad = _module_level_import_roots(path) & _FORBIDDEN_TOP_LEVEL
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"forbidden top-level imports: {offenders}"


def test_no_camoufox_or_playwright_import_named_anywhere_in_cli() -> None:
    # Defense in depth: even lazy `import camoufox` is disallowed in cli/*;
    # the CLI reaches Camoufox only via `from sightstalker.engines import ...`.
    offenders: list[str] = []
    for path in _cli_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"camoufox", "playwright"}:
                        offenders.append(path.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in {
                    "camoufox",
                    "playwright",
                }:
                    offenders.append(path.name)
    assert not offenders, f"browser imports in cli/: {offenders}"


def test_importing_cli_main_does_not_load_browser_or_web() -> None:
    import subprocess

    probe = (
        "import sys, sightstalker.cli.main;"
        "bad=[m for m in ('camoufox','playwright','sightstalker.engines.camoufox',"
        "'fastapi','uvicorn','loguru','tenacity') if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_version_and_config_do_not_load_browser_adapter() -> None:
    import subprocess

    probe = (
        "import sys;"
        "from typer.testing import CliRunner;"
        "from sightstalker.cli.main import app;"
        "r=CliRunner();"
        "assert r.invoke(app,['version','--json']).exit_code==0;"
        "assert r.invoke(app,['config','show','--json']).exit_code==0;"
        "bad=[m for m in ('camoufox','sightstalker.engines.camoufox')"
        " if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
