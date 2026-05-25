"""
sightstalker.environment.applicators — apply an EnvironmentProfile to context config.

Pure, deterministic, side-effect-free. Uses ``model_copy`` and never mutates the
input config. Applies only environment fields (user_agent, viewport, locale,
timezone_id, color_scheme, reduced_motion) plus the ``environment_profile_id``
provenance marker. Navigator metadata is never applied, and no scripts/page
state are touched.
"""

from __future__ import annotations

from sightstalker.environment.models import EnvironmentProfile
from sightstalker.models.browser import BrowserContextConfig

# Context fields an environment profile may contribute (excludes provenance).
ENVIRONMENT_CONTEXT_FIELDS: tuple[str, ...] = (
    "color_scheme",
    "locale",
    "reduced_motion",
    "timezone_id",
    "user_agent",
    "viewport",
)


class DefaultEnvironmentProfileApplicator:
    """Apply an EnvironmentProfile onto a BrowserContextConfig immutably."""

    def apply(
        self,
        *,
        base: BrowserContextConfig,
        environment: EnvironmentProfile,
    ) -> BrowserContextConfig:
        updates: dict[str, object] = {}
        for field in ENVIRONMENT_CONTEXT_FIELDS:
            value = getattr(environment, field)
            if value is not None:
                updates[field] = value
        updates["environment_profile_id"] = environment.profile_id
        return base.model_copy(update=updates)


__all__ = [
    "ENVIRONMENT_CONTEXT_FIELDS",
    "DefaultEnvironmentProfileApplicator",
]
