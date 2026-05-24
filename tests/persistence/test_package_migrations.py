"""Package migration inclusion + clean-install Alembic tests (spec 19.14).

These tests build the project's sdist and wheel into a temporary directory and
install them into throwaway virtualenvs to prove the packaged migrations work
from an installed distribution (not just a source checkout).
"""

from __future__ import annotations

import subprocess
import tarfile
import venv
import zipfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BAD_ARCHIVE_TOKENS = (
    ".venv/",
    ".pytest_cache/",
    "__pycache__/",
    "dist/",
    ".pyc",
    "{models,engines,security}",
)


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--out-dir", str(out)],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    sdist = next(out.glob("sightstalker-*.tar.gz"))
    wheel = next(out.glob("sightstalker-*.whl"))
    return {"sdist": sdist, "wheel": wheel, "dir": out}


def _make_venv(path: Path) -> Path:
    venv.create(path, with_pip=True)
    py = path / "bin" / "python"
    return py


def _alembic_smoke(python: Path, tmp_db: Path) -> str:
    code = (
        "from sightstalker.persistence import make_alembic_config\n"
        "from alembic import command\n"
        f"cfg = make_alembic_config('sqlite+aiosqlite:///{tmp_db}')\n"
        "command.upgrade(cfg, 'head')\n"
        "command.downgrade(cfg, 'base')\n"
        "print('ALEMBIC_OK')\n"
    )
    result = subprocess.run(
        [str(python), "-c", code], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_sdist_includes_migration_files(built_dist: dict[str, Path]) -> None:
    with tarfile.open(built_dist["sdist"]) as tf:
        names = tf.getnames()
    assert any("persistence/migrations/env.py" in n for n in names)
    assert any(
        "persistence/migrations/versions/0001_persistence_1_initial.py" in n
        for n in names
    )
    assert any("persistence/migrations/script.py.mako" in n for n in names)


def test_wheel_includes_migration_files(built_dist: dict[str, Path]) -> None:
    with zipfile.ZipFile(built_dist["wheel"]) as zf:
        names = zf.namelist()
    assert any("persistence/migrations/env.py" in n for n in names)
    assert any(
        "persistence/migrations/versions/0001_persistence_1_initial.py" in n
        for n in names
    )
    assert any("persistence/migrations/script.py.mako" in n for n in names)


def test_archives_have_no_bad_tokens(built_dist: dict[str, Path]) -> None:
    with tarfile.open(built_dist["sdist"]) as tf:
        sdist_names = tf.getnames()
    with zipfile.ZipFile(built_dist["wheel"]) as zf:
        wheel_names = zf.namelist()
    for names in (sdist_names, wheel_names):
        for name in names:
            for bad in _BAD_ARCHIVE_TOKENS:
                assert bad not in name, f"bad token {bad} in {name}"


def test_migration_location_points_to_installed_resources() -> None:
    from sightstalker.persistence import make_alembic_config
    import sightstalker.persistence as pkg

    cfg = make_alembic_config("sqlite+aiosqlite:///:memory:")
    location = Path(cfg.get_main_option("script_location") or "")
    pkg_root = Path(pkg.__file__).parent
    assert location == pkg_root / "migrations"


def test_clean_wheel_install_alembic(
    built_dist: dict[str, Path], tmp_path: Path
) -> None:
    env_dir = tmp_path / "wheel-venv"
    python = _make_venv(env_dir)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", str(built_dist["wheel"])],
        check=True,
        capture_output=True,
        text=True,
    )
    out = _alembic_smoke(python, tmp_path / "wheel.db")
    assert out == "ALEMBIC_OK"


def test_clean_sdist_install_alembic(
    built_dist: dict[str, Path], tmp_path: Path
) -> None:
    env_dir = tmp_path / "sdist-venv"
    python = _make_venv(env_dir)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", str(built_dist["sdist"])],
        check=True,
        capture_output=True,
        text=True,
    )
    out = _alembic_smoke(python, tmp_path / "sdist.db")
    assert out == "ALEMBIC_OK"


def test_installed_version_is_correct(
    built_dist: dict[str, Path], tmp_path: Path
) -> None:
    env_dir = tmp_path / "ver-venv"
    python = _make_venv(env_dir)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", str(built_dist["wheel"])],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import sightstalker, sightstalker.persistence;"
            "print(sightstalker.__version__)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "0.3.1"
