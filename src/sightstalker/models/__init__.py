"""
sightstalker.models — public contract model surface.

Import from this package rather than from submodules directly:

    from sightstalker.models import BrowserLaunchConfig, RunRecord, ArtifactRef
"""

from __future__ import annotations

from sightstalker.models.artifacts import (
    ArtifactRef,
    DiagnosticArtifact,
    ScreenshotArtifact,
    StorageStateArtifact,
    TraceArtifact,
)
from sightstalker.models.base import (
    JsonArray,
    JsonObject,
    JsonValue,
    MutableToolkitModel,
    TimestampedModel,
    ToolkitModel,
    utc_now,
)
from sightstalker.models.browser import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    BrowserState,
    FingerprintConfig,
    ProxyConfig,
    ViewportConfig,
    ViewportPreset,
)
from sightstalker.models.identifiers import (
    ArtifactId,
    ArtifactType,
    BrowserEngineName,
    BrowserMode,
    ContextId,
    FingerprintProfileId,
    HashAlgorithm,
    HealthStatus,
    ProfileId,
    ProxyProfileId,
    RunId,
    RunStatus,
    SessionId,
    StorageStateArtifactType,
)
from sightstalker.models.runs import (
    BrowserContextRecord,
    RunRecord,
    RunRequest,
    RunResult,
)
from sightstalker.models.sessions import (
    ProfileRecord,
    SessionConfig,
    SessionHealthRecord,
    SessionRecord,
)

__all__ = [
    # base
    "JsonArray",
    "JsonObject",
    "JsonValue",
    "MutableToolkitModel",
    "TimestampedModel",
    "ToolkitModel",
    "utc_now",
    # identifiers
    "ArtifactId",
    "ArtifactType",
    "BrowserEngineName",
    "BrowserMode",
    "ContextId",
    "FingerprintProfileId",
    "HashAlgorithm",
    "HealthStatus",
    "ProfileId",
    "ProxyProfileId",
    "RunId",
    "RunStatus",
    "SessionId",
    "StorageStateArtifactType",
    # browser
    "BrowserContextConfig",
    "BrowserLaunchConfig",
    "BrowserState",
    "FingerprintConfig",
    "ProxyConfig",
    "ViewportConfig",
    "ViewportPreset",
    # artifacts
    "ArtifactRef",
    "DiagnosticArtifact",
    "ScreenshotArtifact",
    "StorageStateArtifact",
    "TraceArtifact",
    # sessions
    "ProfileRecord",
    "SessionConfig",
    "SessionHealthRecord",
    "SessionRecord",
    # runs
    "BrowserContextRecord",
    "RunRecord",
    "RunRequest",
    "RunResult",
]
