"""Import-boundary tests for the environment package."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import sightstalker.environment as env_pkg

_ENV_DIR = Path(env_pkg.__file__).parent

_FORBIDDEN_PREFIXES = {
    "sightstalker.engines.camoufox",
    "camoufox",
    "playwright",
    "sightstalker.cli",
    "sightstalker.persistence",
    "sightstalker.interaction",
    "sightstalker.sessions.manager",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_environment_has_no_forbidden_imports() -> None:
    offenders: dict[str, set[str]] = {}
    files = sorted(_ENV_DIR.rglob("*.py"))
    assert files
    for path in files:
        bad: set[str] = set()
        for mod in _imports(path):
            for prefix in _FORBIDDEN_PREFIXES:
                if mod == prefix or mod.startswith(prefix + "."):
                    bad.add(mod)
        if bad:
            offenders[path.name] = bad
    assert offenders == {}, f"environment imports forbidden modules: {offenders}"


def test_environment_subprocess_no_browser_or_cli() -> None:
    probe = (
        "import sys, sightstalker.environment;"
        "bad=[m for m in ('camoufox','playwright','sightstalker.engines.camoufox')"
        " if m in sys.modules];"
        "cli=[m for m in sys.modules if m.startswith('sightstalker.cli')];"
        "print(','.join(bad+cli));"
        "sys.exit(1 if (bad or cli) else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_environment_does_not_import_sessions_manager() -> None:
    for path in sorted(_ENV_DIR.rglob("*.py")):
        for mod in _imports(path):
            assert mod != "sightstalker.sessions.manager"
            assert not mod.startswith("sightstalker.sessions.manager.")
