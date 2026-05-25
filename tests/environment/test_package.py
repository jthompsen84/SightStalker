"""Package-level tests for sightstalker.environment."""

from __future__ import annotations

import subprocess
import sys


def test_environment_imports_without_browser_packages() -> None:
    probe = (
        "import sys, sightstalker.environment;"
        "bad=[m for m in ('camoufox','playwright',"
        "'sightstalker.engines.camoufox') if m in sys.modules];"
        "print(','.join(bad));"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_environment_exports_resolve() -> None:
    import sightstalker.environment as env

    for name in env.__all__:
        assert hasattr(env, name), f"missing export: {name}"


def test_fingerprint_profile_not_exported() -> None:
    import sightstalker.environment as env

    assert "FingerprintProfile" not in env.__all__
    assert not hasattr(env, "FingerprintProfile")


def test_public_concept_is_environment_profile() -> None:
    from sightstalker.environment import EnvironmentProfile

    assert EnvironmentProfile.__name__ == "EnvironmentProfile"


def test_required_public_names_present() -> None:
    import sightstalker.environment as env

    required = {
        "EnvironmentProfile",
        "NavigatorProfile",
        "ContextConfigResolution",
        "ContextConfigResolver",
        "DefaultContextConfigResolver",
        "EnvironmentProfileStore",
        "EnvironmentProfileSelector",
        "EnvironmentProfileApplicator",
        "InMemoryEnvironmentProfileStore",
        "NullEnvironmentProfileStore",
        "DefaultEnvironmentProfileSelector",
        "DefaultEnvironmentProfileApplicator",
        "RunConfigOverrides",
        "LaunchConfigOverrides",
        "ContextConfigOverrides",
        "EnvironmentResolutionOverrides",
        "EnvironmentConfigurationError",
        "EnvironmentProfileNotFound",
    }
    missing = {n for n in required if not hasattr(env, n)}
    assert missing == set(), f"missing exports: {missing}"
