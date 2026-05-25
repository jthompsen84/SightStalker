"""
sightstalker.ops.plans — generic run-plan abstractions.

These are the presentation-neutral plan types shared by all managed runs.
Concrete command plans (run-open, screenshot/trace/console) stay in their CLI
command modules; this module owns only the generic ``Plan`` alias and the
``PlanResult`` container.

``PlanResult.extra`` is operator-output metadata. It is typed as a JSON object
and must be JSON-safe and already operator-sanitized by the plan; ops applies an
additional sanitization/rejection floor before merging it into public output.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

from sightstalker.models import ArtifactRef

if TYPE_CHECKING:
    from sightstalker.ops.surface import RunSurface

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _empty_diagnostics() -> list[tuple[ArtifactRef, int]]:
    return []


def _empty_extra() -> JsonObject:
    return {}


@dataclass
class PlanResult:
    """Output of a capture plan.

    ``extra`` is operator-output metadata. It must be JSON-safe and already
    operator-sanitized by the plan; ops may additionally sanitize or reject it
    before merging into public output.
    """

    title: str | None = None
    final_url: str | None = None
    diagnostics: list[tuple[ArtifactRef, int]] = field(
        default_factory=_empty_diagnostics
    )
    extra: JsonObject = field(default_factory=_empty_extra)


Plan = Callable[["RunSurface"], Awaitable[PlanResult]]

__all__ = ["JsonObject", "JsonValue", "Plan", "PlanResult"]
