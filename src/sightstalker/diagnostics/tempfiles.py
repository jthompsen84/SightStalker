"""
sightstalker.diagnostics.tempfiles — hardened temporary files for capture.

Browser writers (screenshot/trace) need a real filesystem path to write to
before the bytes are read back and handed to the ``ArtifactManager``. This
module provides a hardened temp file with:

- a private per-capture temp directory (0o700),
- exclusive creation of the temp file (O_CREAT | O_EXCL, 0o600),
- symlink rejection on the created path,
- best-effort cleanup.

Absolute temp paths are internal only and must never appear in public error
messages.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sightstalker.diagnostics.errors import DiagnosticCaptureError


class HardenedTempFile:
    """A hardened temp file living inside a private temp directory."""

    def __init__(self, directory: Path, path: Path) -> None:
        self._directory = directory
        self._path = path

    @property
    def path(self) -> Path:
        """Absolute path to the temp file (internal use only)."""
        return self._path

    def read_bytes(self) -> bytes:
        """Read the temp file's bytes, rejecting symlinked targets."""
        if self._path.is_symlink():
            raise DiagnosticCaptureError("diagnostic temp file is a symlink")
        try:
            return self._path.read_bytes()
        except OSError:
            raise DiagnosticCaptureError(
                "diagnostic temp file could not be read"
            ) from None

    def cleanup(self) -> None:
        """Best-effort removal of the temp file and its private directory."""
        try:
            if self._path.exists() or self._path.is_symlink():
                self._path.unlink()
        except OSError:
            pass
        try:
            self._directory.rmdir()
        except OSError:
            pass


@contextmanager
def hardened_temp_file(*, suffix: str) -> Generator[HardenedTempFile]:
    """Create a hardened temp file, yield it, and clean it up on exit.

    The file is created exclusively with restrictive permissions inside a
    private 0o700 directory. The suffix is used only for the temp file name.
    """
    safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    if "/" in safe_suffix or "\\" in safe_suffix or "\x00" in safe_suffix:
        raise DiagnosticCaptureError("diagnostic temp suffix is invalid")

    directory = Path(tempfile.mkdtemp(prefix="sightstalker-diag-"))
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

    target = directory / f"capture{safe_suffix}"
    try:
        fd = os.open(
            target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except OSError:
        try:
            directory.rmdir()
        except OSError:
            pass
        raise DiagnosticCaptureError(
            "diagnostic temp file could not be created"
        ) from None
    os.close(fd)

    if target.is_symlink():
        try:
            target.unlink()
            directory.rmdir()
        except OSError:
            pass
        raise DiagnosticCaptureError("diagnostic temp file is a symlink")

    handle = HardenedTempFile(directory, target)
    try:
        yield handle
    finally:
        handle.cleanup()
