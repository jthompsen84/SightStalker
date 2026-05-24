"""
sightstalker.sessions.state_store — immutable per-run storage-state snapshots.

This is a narrow, storage-state-specific store. It writes
``storage_state.initial.json`` / ``storage_state.final.json`` under a run
directory with exclusive-create / no-clobber semantics and returns an
``ArtifactRef`` with a relative path, SHA-256, and size.

As of ``ARTIFACTS-1`` (v0.2.1) the actual file writing, reading, hashing, MIME
inference, and path-containment work is delegated to ``ArtifactManager``. This
module keeps its narrow public API and its ``SessionStateError`` exception
contract: every artifact-layer failure is caught and re-raised as a sanitized
``SessionStateError`` so that callers see no behavior change and no payload or
absolute-path leakage.

Storage-state files may contain cookies and local storage; they are sensitive.
Payloads are never logged, printed, or embedded in exception strings.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from sightstalker.artifacts import ArtifactError, ArtifactManager, ArtifactPaths
from sightstalker.models import (
    ArtifactRef,
    BrowserState,
    ProfileId,
    RunId,
    SessionId,
    StorageStateArtifactType,
)
from sightstalker.sessions.errors import SessionStateError
from sightstalker.sessions.ids import (
    new_artifact_id,
    validate_profile_id,
    validate_run_id,
)
from sightstalker.sessions.paths import SessionPaths

_INITIAL: StorageStateArtifactType = "storage_state_initial"
_FINAL: StorageStateArtifactType = "storage_state_final"

_PREFIX_FOR_TYPE: dict[StorageStateArtifactType, str] = {
    _INITIAL: "init",
    _FINAL: "final",
}


class BrowserStateStore:
    """Writes/reads immutable per-run browser storage-state JSON files.

    File writing/reading is delegated to ``ArtifactManager``; this store owns
    only storage-state naming, identifiers, and the ``SessionStateError``
    contract.
    """

    def __init__(
        self,
        paths: SessionPaths,
        *,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self._paths = paths
        # The artifact manager shares the session data directory as its root so
        # that relative artifact paths and the session layout coincide.
        self._manager = (
            artifact_manager
            if artifact_manager is not None
            else ArtifactManager(ArtifactPaths(paths.data_dir))
        )

    # ------------------------------------------------------------------
    # Path helper
    # ------------------------------------------------------------------

    def state_path_for(
        self,
        *,
        profile_id: ProfileId,
        run_id: RunId,
        artifact_type: StorageStateArtifactType,
    ) -> Path:
        validated_profile = validate_profile_id(profile_id)
        validated_run = validate_run_id(run_id)
        if artifact_type == _INITIAL:
            return self._paths.storage_state_initial_path(
                validated_profile, validated_run
            )
        if artifact_type == _FINAL:
            return self._paths.storage_state_final_path(
                validated_profile, validated_run
            )
        raise SessionStateError("unsupported storage-state artifact type")

    def _relative_state_path(
        self,
        *,
        profile_id: ProfileId,
        run_id: RunId,
        artifact_type: StorageStateArtifactType,
    ) -> Path:
        target = self.state_path_for(
            profile_id=profile_id,
            run_id=run_id,
            artifact_type=artifact_type,
        )
        try:
            return self._paths.relative_to_data_dir(target)
        except ValueError:
            raise SessionStateError("storage-state path is unsafe") from None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def write_initial_state(
        self,
        *,
        profile_id: ProfileId,
        run_id: RunId,
        session_id: SessionId | None,
        state: BrowserState,
    ) -> ArtifactRef:
        return self.write_state(
            profile_id=profile_id,
            run_id=run_id,
            session_id=session_id,
            state=state,
            artifact_type=_INITIAL,
        )

    def write_final_state(
        self,
        *,
        profile_id: ProfileId,
        run_id: RunId,
        session_id: SessionId | None,
        state: BrowserState,
    ) -> ArtifactRef:
        return self.write_state(
            profile_id=profile_id,
            run_id=run_id,
            session_id=session_id,
            state=state,
            artifact_type=_FINAL,
        )

    def write_state(
        self,
        *,
        profile_id: ProfileId,
        run_id: RunId,
        session_id: SessionId | None,
        state: BrowserState,
        artifact_type: StorageStateArtifactType,
    ) -> ArtifactRef:
        relative = self._relative_state_path(
            profile_id=profile_id,
            run_id=run_id,
            artifact_type=artifact_type,
        )
        # Preserve the SESSION-STATE-1 artifact-id prefixes ("init"/"final").
        artifact_id = new_artifact_id(_PREFIX_FOR_TYPE[artifact_type])
        payload = state.model_dump(mode="json")
        try:
            return self._manager.write_json(
                relative_path=relative,
                artifact_type=artifact_type,
                payload=payload,
                artifact_id=artifact_id,
            )
        except ArtifactError:
            raise SessionStateError(
                "storage-state artifact could not be written"
            ) from None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def read_state(self, ref: ArtifactRef) -> BrowserState:
        if ref.artifact_type not in (_INITIAL, _FINAL):
            raise SessionStateError("artifact_type is not a storage-state type")

        try:
            data = self._manager.read_json(ref)
        except ArtifactError:
            raise SessionStateError(
                "storage-state artifact could not be read"
            ) from None

        if not isinstance(data, dict):
            raise SessionStateError("storage-state payload is not a JSON object")

        try:
            return BrowserState.model_validate(data)
        except ValidationError:
            raise SessionStateError("storage-state failed validation") from None
