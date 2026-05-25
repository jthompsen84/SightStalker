"""
sightstalker.environment.errors — sanitized environment configuration errors.

These classify publicly as ``UsageError`` (exit code 2) and carry only
sanitized messages: never raw profile JSON, user agents, headers, tokens,
cookies, or secrets.
"""

from __future__ import annotations

from sightstalker.resilience.errors import UsageError


class EnvironmentConfigurationError(UsageError):
    """Invalid environment profile or environment resolution configuration."""


class EnvironmentProfileNotFound(EnvironmentConfigurationError):
    """Requested environment profile id was not found."""


__all__ = [
    "EnvironmentConfigurationError",
    "EnvironmentProfileNotFound",
]
