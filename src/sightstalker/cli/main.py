"""
sightstalker.cli.main — console-script entrypoint.

The ``sightstalker`` console script targets ``sightstalker.cli.main:app``.
Importing this module must not import any browser package/adapter or web
framework; the browser engine is resolved lazily only when a browser command
runs.
"""

from __future__ import annotations

from sightstalker.cli.app import app

__all__ = ["app"]


if __name__ == "__main__":  # pragma: no cover
    app()
