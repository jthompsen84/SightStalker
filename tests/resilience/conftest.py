"""Resilience test fixtures.

The CLI-integration tests reuse the protocol-compliant fakes and fixtures from
the CLI test conftest. ``pytest_plugins`` is only allowed in a top-level
conftest, so instead the fixture functions are imported and re-registered here.
"""

from __future__ import annotations

from tests.cli.conftest import (
    cli_config,
    fake_engine,
    initialized_config,
    patch_engine,
    profile_and_session,
    runner,
)

__all__ = [
    "cli_config",
    "fake_engine",
    "initialized_config",
    "patch_engine",
    "profile_and_session",
    "runner",
]
