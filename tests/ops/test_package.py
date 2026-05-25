"""Package-level tests for sightstalker.ops."""

from __future__ import annotations

import subprocess
import sys

import sightstalker


def test_version_is_0_4_5() -> None:
    assert sightstalker.__version__ == "0.4.5"


def test_ops_exports() -> None:
    import sightstalker.ops as ops

    assert hasattr(ops, "EngineFactory")
    assert hasattr(ops, "Plan")
    assert hasattr(ops, "PlanResult")
    assert hasattr(ops, "RunSurface")
    assert hasattr(ops, "execute_managed_run")
    assert hasattr(ops, "ManagedRunResult")


def test_ops_all_resolves() -> None:
    import sightstalker.ops as ops

    for name in ops.__all__:
        assert hasattr(ops, name), f"missing export: {name}"


def test_importing_ops_does_not_load_camoufox_or_playwright() -> None:
    probe = (
        "import sys, sightstalker.ops;"
        "bad=[m for m in ('camoufox','playwright',"
        "'sightstalker.engines.camoufox','typer','rich') if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
