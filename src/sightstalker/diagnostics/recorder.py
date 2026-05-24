"""
sightstalker.diagnostics.recorder — diagnostic artifact recorder.

The recorder generates exactly one artifact ID per diagnostic, embeds it in the
relative path (via ``DiagnosticPathPolicy``), and passes the *same* ID to
``ArtifactManager.write_*`` so the path-embedded ID equals
``ArtifactRef.artifact_id``.

Local writes are synchronous and return ``DiagnosticArtifactResult(persisted=
False)``. Optional metadata persistence is an explicit async step through an
injected repository-like protocol; persistence never commits, never mutates
run/session records, and never deletes the artifact on failure (orphan policy).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sightstalker.artifacts import ArtifactManager
from sightstalker.diagnostics.errors import DiagnosticPersistenceError
from sightstalker.diagnostics.models import (
    DiagnosticArtifactResult,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
)
from sightstalker.diagnostics.paths import DiagnosticPathPolicy
from sightstalker.ids import new_artifact_id
from sightstalker.models import ArtifactRef, ArtifactType, RunId, SessionId

if TYPE_CHECKING:
    pass


class ArtifactPersistenceProtocol(Protocol):
    """Repository-like artifact metadata sink (no SQLAlchemy import)."""

    async def create(
        self,
        ref: ArtifactRef,
        *,
        session_id: SessionId | None = None,
        run_id: RunId | None = None,
        run_order: int | None = None,
    ) -> ArtifactRef: ...


_KIND_FOR_TYPE = {
    "screenshot": "screenshot",
    "trace": "trace",
    "run_log": "console",
}

_PREFIX_FOR_KIND = {
    "screenshot": "screenshot",
    "trace": "trace",
    "console": "console",
}


class DiagnosticArtifactRecorder:
    """Writes diagnostic artifacts through ``ArtifactManager`` with stable IDs."""

    def __init__(
        self,
        manager: ArtifactManager,
        *,
        path_policy: DiagnosticPathPolicy | None = None,
        artifact_persistence: ArtifactPersistenceProtocol | None = None,
    ) -> None:
        self._manager = manager
        self._paths = path_policy or DiagnosticPathPolicy()
        self._persistence = artifact_persistence

    def _build_path(
        self,
        *,
        artifact_id: str,
        artifact_type: ArtifactType,
        suffix: str,
        target: DiagnosticTarget,
    ) -> Path:
        kind = _KIND_FOR_TYPE[artifact_type]
        return self._paths.artifact_relative_path(
            artifact_id=artifact_id,
            kind=kind,
            suffix=suffix,
            run_id=target.run_id,
        )

    def write_bytes(
        self,
        *,
        data: bytes,
        artifact_type: ArtifactType,
        suffix: str,
        target: DiagnosticTarget,
        mime_type: str | None = None,
    ) -> DiagnosticArtifactResult:
        """Write diagnostic bytes locally; returns ``persisted=False``."""
        kind = _KIND_FOR_TYPE[artifact_type]
        artifact_id = new_artifact_id(_PREFIX_FOR_KIND[kind])
        rel = self._build_path(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            suffix=suffix,
            target=target,
        )
        ref = self._manager.write_bytes(
            relative_path=rel,
            artifact_type=artifact_type,
            data=data,
            artifact_id=artifact_id,
            mime_type=mime_type,
        )
        return DiagnosticArtifactResult(
            artifact_ref=ref, target=target, persisted=False
        )

    def write_text(
        self,
        *,
        text: str,
        artifact_type: ArtifactType,
        suffix: str,
        target: DiagnosticTarget,
        mime_type: str | None = None,
    ) -> DiagnosticArtifactResult:
        """Write diagnostic text locally; returns ``persisted=False``."""
        kind = _KIND_FOR_TYPE[artifact_type]
        artifact_id = new_artifact_id(_PREFIX_FOR_KIND[kind])
        rel = self._build_path(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            suffix=suffix,
            target=target,
        )
        ref = self._manager.write_text(
            relative_path=rel,
            artifact_type=artifact_type,
            text=text,
            artifact_id=artifact_id,
            mime_type=mime_type,
        )
        return DiagnosticArtifactResult(
            artifact_ref=ref, target=target, persisted=False
        )

    async def persist_artifact_result(
        self,
        result: DiagnosticArtifactResult,
        policy: DiagnosticPersistencePolicy,
    ) -> DiagnosticArtifactResult:
        """Optionally persist artifact metadata through the injected repo.

        Does not commit. On failure the artifact file remains (orphan policy)
        and a sanitized ``DiagnosticPersistenceError`` is raised.
        """
        if not policy.persist_artifact_metadata:
            return result
        if self._persistence is None:
            raise DiagnosticPersistenceError(
                "artifact persistence requested but no repository was provided"
            )
        target = result.target
        if target.run_id is not None and target.run_order is None:
            raise DiagnosticPersistenceError(
                "run_order is required to persist a run-scoped artifact"
            )
        try:
            await self._persistence.create(
                result.artifact_ref,
                session_id=target.session_id,
                run_id=target.run_id,
                run_order=target.run_order,
            )
        except DiagnosticPersistenceError:
            raise
        except Exception as exc:
            raise DiagnosticPersistenceError(
                f"artifact metadata persistence failed: {type(exc).__name__}"
            ) from None
        return result.model_copy(update={"persisted": True})
