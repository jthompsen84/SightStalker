from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ToolkitModel(BaseModel):
    """
    Base model for internal immutable contract objects.

    Policy:
    - No silent extra fields (extra="forbid").
    - No arbitrary mutation after construction (frozen=True).
    - Do not expose raw validation inputs in errors (hide_input_in_errors=True).
    - Validate default values (validate_default=True).
    - Strip surrounding whitespace from strings (str_strip_whitespace=True).
    - No arbitrary third-party types (arbitrary_types_allowed=False).

    Prefer this base for all domain objects, configs, and records.
    Use MutableToolkitModel only when mutation is explicitly required.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=False,
    )


class MutableToolkitModel(BaseModel):
    """
    Explicit escape hatch for stateful builder or configuration cases.

    Prefer ToolkitModel unless mutation is required.
    This model validates on assignment but is not frozen.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_default=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
        arbitrary_types_allowed=False,
    )


class TimestampedModel(ToolkitModel):
    """
    Immutable model with automatic UTC created_at and optional updated_at.

    Both timestamps are timezone-aware.
    """

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# JSON type aliases
# ---------------------------------------------------------------------------

JsonObject = dict[str, Any]
JsonArray = list[Any]
JsonValue = str | int | float | bool | None | dict[str, Any] | list[Any]
