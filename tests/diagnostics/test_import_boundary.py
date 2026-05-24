"""Import-boundary tests for diagnostics (spec §19)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import sightstalker.diagnostics as diagnostics_pkg

_PROHIBITED = (
    "camoufox",
    "playwright",
    "typer",
    "rich",
    "loguru",
    "tenacity",
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "sightstalker.engines.camoufox",
    "sightstalker.sessions.manager",
)


def _diagnostics_root() -> Path:
    return Path(diagnostics_pkg.__file__).parent


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
    return found


def _subprocess_modules_after(import_line: str) -> set[str]:
    code = (
        f"import sys\n{import_line}\n"
        "mods = [m for m in ("
        "'sqlalchemy','alembic','camoufox','playwright',"
        "'sightstalker.engines.camoufox') if m in sys.modules]\n"
        "print(','.join(mods))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    return {m for m in result.stdout.strip().split(",") if m}


def test_import_diagnostics_works() -> None:
    import sightstalker.diagnostics  # noqa: F401

    assert sightstalker.diagnostics is not None


def test_import_diagnostics_no_browser_or_sql() -> None:
    loaded = _subprocess_modules_after("import sightstalker.diagnostics")
    assert loaded == set(), f"unexpected modules loaded: {loaded}"


def test_import_diagnostics_no_camoufox_adapter() -> None:
    loaded = _subprocess_modules_after("import sightstalker.diagnostics")
    assert "sightstalker.engines.camoufox" not in loaded
    assert "camoufox" not in loaded
    assert "playwright" not in loaded


def test_import_diagnostics_no_sqlalchemy_alembic() -> None:
    loaded = _subprocess_modules_after("import sightstalker.diagnostics")
    assert "sqlalchemy" not in loaded
    assert "alembic" not in loaded


def _assert_no_prohibited(substr: str) -> None:
    root = _diagnostics_root()
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert substr not in module, f"{path.name} imports {module}"


def test_ast_no_camoufox() -> None:
    _assert_no_prohibited("camoufox")


def test_ast_no_playwright() -> None:
    _assert_no_prohibited("playwright")


def test_ast_no_sqlalchemy() -> None:
    _assert_no_prohibited("sqlalchemy")


def test_ast_no_alembic() -> None:
    _assert_no_prohibited("alembic")


def test_ast_no_typer_rich_loguru() -> None:
    _assert_no_prohibited("typer")
    _assert_no_prohibited("rich")
    _assert_no_prohibited("loguru")


def test_ast_no_fastapi_uvicorn() -> None:
    _assert_no_prohibited("fastapi")
    _assert_no_prohibited("uvicorn")


def test_ast_no_sessions_manager() -> None:
    _assert_no_prohibited("sessions.manager")


def test_ast_does_not_import_engines_package_directly() -> None:
    # Diagnostics must import from sightstalker.engines.base only, never the
    # engines package root or the camoufox adapter.
    root = _diagnostics_root()
    for path in _python_files(root):
        for module in _imported_modules(path):
            if module == "sightstalker.engines":
                raise AssertionError(
                    f"{path.name} imports sightstalker.engines package root"
                )
            if module == "sightstalker.engines.camoufox":
                raise AssertionError(f"{path.name} imports camoufox adapter")


def test_ast_full_prohibited_set() -> None:
    root = _diagnostics_root()
    for path in _python_files(root):
        modules = _imported_modules(path)
        for prohibited in _PROHIBITED:
            assert prohibited not in modules, (
                f"{path.name} imports prohibited module {prohibited}"
            )


def test_allowed_imports_present() -> None:
    # Sanity: diagnostics DOES use the accepted protocol module and artifacts.
    root = _diagnostics_root()
    all_imports: set[str] = set()
    for path in _python_files(root):
        all_imports |= _imported_modules(path)
    assert "sightstalker.engines.base" in all_imports
    assert any(m.startswith("sightstalker.artifacts") for m in all_imports)
