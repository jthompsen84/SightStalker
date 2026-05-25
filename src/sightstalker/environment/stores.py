"""
sightstalker.environment.stores — programmatic / null / in-memory profile stores.

ENVIRONMENT-1 ships no opinionated builtin identity presets. Stores never read
or write files and never import persistence. Static profiles for tests live in
the tests, not here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sightstalker.environment.errors import EnvironmentProfileNotFound
from sightstalker.environment.models import EnvironmentProfile
from sightstalker.models.identifiers import FingerprintProfileId


class InMemoryEnvironmentProfileStore:
    """In-memory store of pre-validated environment profiles (programmatic)."""

    def __init__(
        self, profiles: Iterable[EnvironmentProfile] | None = None
    ) -> None:
        self._profiles: dict[str, EnvironmentProfile] = {}
        for profile in profiles or ():
            self._profiles[profile.profile_id] = profile

    def add(self, profile: EnvironmentProfile) -> None:
        self._profiles[profile.profile_id] = profile

    async def load(self, profile_id: FingerprintProfileId) -> EnvironmentProfile:
        try:
            return self._profiles[profile_id]
        except KeyError:
            raise EnvironmentProfileNotFound(
                "environment profile not found"
            ) from None

    @classmethod
    def from_mapping(
        cls, mapping: Mapping[str, EnvironmentProfile]
    ) -> InMemoryEnvironmentProfileStore:
        store = cls()
        for profile in mapping.values():
            store.add(profile)
        return store


class NullEnvironmentProfileStore:
    """A store that holds no profiles; every load fails as not-found."""

    async def load(self, profile_id: FingerprintProfileId) -> EnvironmentProfile:
        raise EnvironmentProfileNotFound("environment profile not found")


__all__ = [
    "InMemoryEnvironmentProfileStore",
    "NullEnvironmentProfileStore",
]
