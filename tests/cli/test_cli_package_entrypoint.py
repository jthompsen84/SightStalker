"""Console-script entrypoint tests, including clean wheel/sdist installs."""

from __future__ import annotations

import json
import subprocess
import venv
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_app_callable_resolves() -> None:
    from sightstalker.cli.main import app

    assert callable(app)


def test_console_script_declared_in_pyproject() -> None:
    text = (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.scripts]" in text
    assert 'sightstalker = "sightstalker.cli.main:app"' in text


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("clidist")
    subprocess.run(
        ["uv", "build", "--out-dir", str(out)],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    sdist = next(out.glob("sightstalker-*.tar.gz"))
    wheel = next(out.glob("sightstalker-*.whl"))
    return {"sdist": sdist, "wheel": wheel}


def _venv_python(path: Path) -> Path:
    venv.create(path, with_pip=True)
    return path / "bin" / "python"


def _install_and_run_version(python: Path, artifact: Path) -> dict[str, object]:
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", str(artifact)],
        check=True,
        capture_output=True,
        text=True,
    )
    script = python.parent / "sightstalker"
    result = subprocess.run(
        [str(script), "version", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_clean_wheel_entrypoint(
    built_dist: dict[str, Path], tmp_path: Path
) -> None:
    python = _venv_python(tmp_path / "wheel-venv")
    payload = _install_and_run_version(python, built_dist["wheel"])
    assert payload["ok"] is True
    assert payload["data"] == {"version": "0.4.5"}


def test_clean_sdist_entrypoint(
    built_dist: dict[str, Path], tmp_path: Path
) -> None:
    python = _venv_python(tmp_path / "sdist-venv")
    payload = _install_and_run_version(python, built_dist["sdist"])
    assert payload["ok"] is True
    assert payload["data"] == {"version": "0.4.5"}
