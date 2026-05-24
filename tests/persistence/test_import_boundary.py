"""Import-boundary tests (spec 19.13)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import sightstalker.persistence as persistence_pkg

_PROHIBITED = (
    "camoufox",
    "playwright",
    "typer",
    "rich",
    "loguru",
    "tenacity",
    "fastapi",
    "uvicorn",
    "sightstalker.engines.camoufox",
    "sightstalker.sessions.manager",
    "sightstalker.artifacts.manager",
)


def _persistence_root() -> Path:
    return Path(persistence_pkg.__file__).parent


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _is_migration_file(path: Path) -> bool:
    return "migrations" in path.parts


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


def _run_subprocess_import_check(import_line: str) -> str:
    code = (
        f"import sys\n{import_line}\n"
        "print('sqlalchemy' in sys.modules, 'alembic' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_import_persistence_works() -> None:
    import sightstalker.persistence  # noqa: F401

    assert sightstalker.persistence is not None


def test_import_sightstalker_no_sqlalchemy_alembic() -> None:
    out = _run_subprocess_import_check("import sightstalker")
    assert out == "False False"


def test_import_models_no_sqlalchemy_alembic() -> None:
    out = _run_subprocess_import_check("import sightstalker.models")
    assert out == "False False"


def test_import_artifacts_no_sqlalchemy_alembic() -> None:
    out = _run_subprocess_import_check("import sightstalker.artifacts")
    assert out == "False False"


def test_import_sessions_no_sqlalchemy_alembic() -> None:
    out = _run_subprocess_import_check("import sightstalker.sessions")
    assert out == "False False"


def test_import_engines_base_no_sqlalchemy_alembic() -> None:
    out = _run_subprocess_import_check("import sightstalker.engines.base")
    assert out == "False False"


def test_fresh_subprocess_all_non_persistence_imports() -> None:
    line = (
        "import sightstalker\n"
        "import sightstalker.models\n"
        "import sightstalker.artifacts\n"
        "import sightstalker.sessions\n"
        "import sightstalker.engines.base"
    )
    out = _run_subprocess_import_check(line)
    assert out == "False False"


def _assert_no_prohibited(substr: str) -> None:
    root = _persistence_root()
    for path in _python_files(root):
        if _is_migration_file(path):
            continue
        for module in _imported_modules(path):
            assert substr not in module, f"{path.name} imports {module}"


def test_ast_no_camoufox() -> None:
    _assert_no_prohibited("camoufox")


def test_ast_no_playwright() -> None:
    _assert_no_prohibited("playwright")


def test_ast_no_typer() -> None:
    _assert_no_prohibited("typer")


def test_ast_no_rich() -> None:
    _assert_no_prohibited("rich")


def test_ast_no_loguru() -> None:
    _assert_no_prohibited("loguru")


def test_ast_no_fastapi_uvicorn() -> None:
    _assert_no_prohibited("fastapi")
    _assert_no_prohibited("uvicorn")


def test_ast_no_sessions_manager() -> None:
    _assert_no_prohibited("sessions.manager")


def test_ast_no_artifacts_manager() -> None:
    _assert_no_prohibited("artifacts.manager")


def test_ast_full_prohibited_set_non_migration() -> None:
    root = _persistence_root()
    for path in _python_files(root):
        if _is_migration_file(path):
            continue
        modules = _imported_modules(path)
        for prohibited in _PROHIBITED:
            assert prohibited not in modules, (
                f"{path.name} imports prohibited module {prohibited}"
            )


def test_migration_files_may_import_sqlalchemy_alembic() -> None:
    # Sanity: migration files are parsed separately and ARE allowed alembic/sa.
    root = _persistence_root()
    migration_files = [p for p in _python_files(root) if _is_migration_file(p)]
    assert migration_files  # there is at least env.py + the version file
    all_imports: set[str] = set()
    for path in migration_files:
        all_imports |= _imported_modules(path)
    assert any("alembic" in m or "sqlalchemy" in m for m in all_imports)
