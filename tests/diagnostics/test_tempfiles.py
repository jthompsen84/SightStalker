"""Temp-file hardening tests (spec §6 tempfiles, §18)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from sightstalker.diagnostics.errors import DiagnosticCaptureError
from sightstalker.diagnostics.tempfiles import hardened_temp_file


def test_temp_file_created_and_readable() -> None:
    with hardened_temp_file(suffix=".png") as temp:
        assert temp.path.exists()
        temp.path.write_bytes(b"data")
        assert temp.read_bytes() == b"data"


def test_temp_file_restrictive_permissions() -> None:
    with hardened_temp_file(suffix=".zip") as temp:
        mode = stat.S_IMODE(os.stat(temp.path).st_mode)
        # Owner-only read/write; no group/other bits.
        assert mode & 0o077 == 0


def test_temp_dir_private() -> None:
    with hardened_temp_file(suffix=".png") as temp:
        parent = temp.path.parent
        mode = stat.S_IMODE(os.stat(parent).st_mode)
        assert mode & 0o077 == 0


def test_cleanup_removes_file_and_dir() -> None:
    captured: Path | None = None
    with hardened_temp_file(suffix=".png") as temp:
        captured = temp.path
        assert captured.exists()
    assert captured is not None
    assert not captured.exists()
    assert not captured.parent.exists()


def test_cleanup_succeeds_even_if_file_already_gone() -> None:
    with hardened_temp_file(suffix=".zip") as temp:
        temp.path.unlink()  # simulate external removal
    # Exiting the context must not raise.


def test_read_symlink_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.bin"
    real.write_bytes(b"x")
    with hardened_temp_file(suffix=".png") as temp:
        # Replace the temp file with a symlink to probe the guard.
        temp.path.unlink()
        temp.path.symlink_to(real)
        with pytest.raises(DiagnosticCaptureError):
            temp.read_bytes()


def test_suffix_with_separators_rejected() -> None:
    with pytest.raises(DiagnosticCaptureError):
        with hardened_temp_file(suffix="a/b.png"):
            pass
