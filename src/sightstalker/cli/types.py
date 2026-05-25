"""
sightstalker.cli.types — shared CLI typed structures and input validators.

Command handlers return a ``CommandOutcome`` (machine-readable ``data`` plus a
human renderer plus warnings). Input validators raise project-owned
``CliUsageError`` / ``CliSecurityError`` so that, under ``--json``, invalid IDs,
URLs, and limits produce the JSON failure envelope rather than a raw Typer
parse error.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from sightstalker.cli.errors import CliUsageError
from sightstalker.models import BrowserEngineName, ProfileId, SessionId
from sightstalker.sessions.ids import validate_profile_id, validate_session_id

# JSON-serializable command payload.
JsonData = dict[str, Any] | list[Any] | None

# A human-output renderer prints Rich content to the given console.
HumanRenderer = Callable[[Console], None]


def _noop_human(console: Console) -> None:  # pragma: no cover - trivial
    return None


def _empty_str_list() -> list[str]:
    return []


@dataclass(frozen=True)
class CommandOutcome:
    """Successful command result: machine data, human renderer, warnings."""

    data: JsonData = None
    human: HumanRenderer = _noop_human
    warnings: list[str] = field(default_factory=_empty_str_list)


# Only "camoufox" is a CLI-supported engine name in CLI-RUNNER-1.
SUPPORTED_ENGINE_NAMES: tuple[str, ...] = ("camoufox",)


def require_profile_id(value: str) -> ProfileId:
    """Validate a profile id argument, raising ``CliUsageError`` on failure."""
    try:
        return validate_profile_id(value)
    except Exception:
        raise CliUsageError("invalid profile id") from None


def require_session_id(value: str) -> SessionId:
    """Validate a session id argument, raising ``CliUsageError`` on failure."""
    try:
        return validate_session_id(value)
    except Exception:
        raise CliUsageError("invalid session id") from None


def optional_profile_id(value: str | None) -> ProfileId | None:
    if value is None or value == "":
        return None
    return require_profile_id(value)


def optional_session_id(value: str | None) -> SessionId | None:
    if value is None or value == "":
        return None
    return require_session_id(value)


def validate_limit(value: int | None) -> int | None:
    """Require a positive limit when provided."""
    if value is None:
        return None
    if value <= 0:
        raise CliUsageError("--limit must be a positive integer")
    return value


def validate_timeout_ms(value: int | None) -> int | None:
    """Require a positive timeout in milliseconds when provided."""
    if value is None:
        return None
    if value <= 0:
        raise CliUsageError("--timeout-ms must be a positive integer")
    return value


def validate_engine_name(value: str) -> BrowserEngineName:
    """Validate a CLI engine option (only ``camoufox`` is supported)."""
    if value not in SUPPORTED_ENGINE_NAMES:
        raise CliUsageError(
            f"unsupported engine '{value}'; supported engines: "
            f"{', '.join(SUPPORTED_ENGINE_NAMES)}"
        )
    return "camoufox"


__all__ = [
    "CommandOutcome",
    "HumanRenderer",
    "JsonData",
    "SUPPORTED_ENGINE_NAMES",
    "optional_profile_id",
    "optional_session_id",
    "require_profile_id",
    "require_session_id",
    "validate_engine_name",
    "validate_limit",
    "validate_timeout_ms",
]
