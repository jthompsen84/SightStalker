"""
sightstalker.environment — environment profile contracts and pre-launch resolution.

Public surface: ``EnvironmentProfile`` and ``NavigatorProfile`` models, the
override/resolution data contracts, the store/selector/applicator/resolver
protocols, programmatic null/in-memory stores, selectors, the default
applicator, the ``DefaultContextConfigResolver``, and sanitized errors.

``EnvironmentProfile`` is the public concept. The internal
``FingerprintProfile`` compatibility alias is intentionally NOT exported. No
fingerprint generation, proxy rotation, navigator injection, or behavior
simulation is implemented here.

Importing this package must not load Camoufox, Playwright, CLI, persistence, or
sessions.manager.
"""

from __future__ import annotations

from sightstalker.environment.applicators import (
    DefaultEnvironmentProfileApplicator,
)
from sightstalker.environment.errors import (
    EnvironmentConfigurationError,
    EnvironmentProfileNotFound,
)
from sightstalker.environment.models import (
    ColorScheme,
    ContextConfigOverrides,
    ContextConfigResolution,
    EnvironmentProfile,
    EnvironmentResolutionOverrides,
    LaunchConfigOverrides,
    NavigatorProfile,
    ReducedMotion,
    RunConfigOverrides,
    validate_user_agent,
)
from sightstalker.environment.protocols import (
    ContextConfigResolver,
    EnvironmentProfileApplicator,
    EnvironmentProfileSelector,
    EnvironmentProfileStore,
)
from sightstalker.environment.resolver import DefaultContextConfigResolver
from sightstalker.environment.selectors import (
    DefaultEnvironmentProfileSelector,
    NullEnvironmentProfileSelector,
    SessionContextEnvironmentProfileSelector,
    StaticEnvironmentProfileSelector,
)
from sightstalker.environment.stores import (
    InMemoryEnvironmentProfileStore,
    NullEnvironmentProfileStore,
)

__all__ = [
    "ColorScheme",
    "ContextConfigOverrides",
    "ContextConfigResolution",
    "ContextConfigResolver",
    "DefaultContextConfigResolver",
    "DefaultEnvironmentProfileApplicator",
    "DefaultEnvironmentProfileSelector",
    "EnvironmentConfigurationError",
    "EnvironmentProfile",
    "EnvironmentProfileApplicator",
    "EnvironmentProfileNotFound",
    "EnvironmentProfileSelector",
    "EnvironmentProfileStore",
    "EnvironmentResolutionOverrides",
    "InMemoryEnvironmentProfileStore",
    "LaunchConfigOverrides",
    "NavigatorProfile",
    "NullEnvironmentProfileSelector",
    "NullEnvironmentProfileStore",
    "ReducedMotion",
    "RunConfigOverrides",
    "SessionContextEnvironmentProfileSelector",
    "StaticEnvironmentProfileSelector",
    "validate_user_agent",
]
