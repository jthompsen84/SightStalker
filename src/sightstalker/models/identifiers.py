from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

# ---------------------------------------------------------------------------
# Typed identifier aliases
#
# All IDs are prefix-namespaced strings validated against a strict pattern.
# Format: <prefix>_<first-alphanum><7-63 alphanum/dash/underscore chars>
#
# Test fixture convention (belongs in tests, not production):
#   prof_test_default, sess_test_default, run_test_default,
#   ctx_test_default, art_test_default, fp_test_default, proxy_test_default
# ---------------------------------------------------------------------------

SessionId = Annotated[
    str,
    StringConstraints(pattern=r"^sess_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

RunId = Annotated[
    str,
    StringConstraints(pattern=r"^run_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

ProfileId = Annotated[
    str,
    StringConstraints(pattern=r"^prof_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

ContextId = Annotated[
    str,
    StringConstraints(pattern=r"^ctx_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

ArtifactId = Annotated[
    str,
    StringConstraints(pattern=r"^art_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

FingerprintProfileId = Annotated[
    str,
    StringConstraints(pattern=r"^fp_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

ProxyProfileId = Annotated[
    str,
    StringConstraints(pattern=r"^proxy_[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
]

# ---------------------------------------------------------------------------
# Literal enumerations
# ---------------------------------------------------------------------------

BrowserEngineName = Literal[
    "camoufox",
    "playwright_chromium",
    "playwright_firefox",
    "playwright_webkit",
    "mock",
]

BrowserMode = Literal["headless", "headed"]

RunStatus = Literal[
    "pending",
    "starting",
    "running",
    "succeeded",
    "failed",
    "cancelled",
]

HealthStatus = Literal[
    "unknown",
    "healthy",
    "degraded",
    "unhealthy",
]

ArtifactType = Literal[
    "screenshot",
    "trace",
    "storage_state_initial",
    "storage_state_final",
    "fingerprint_profile",
    "run_log",
    "diagnostic_bundle",
]

StorageStateArtifactType = Literal[
    "storage_state_initial",
    "storage_state_final",
]

HashAlgorithm = Literal["sha256"]
