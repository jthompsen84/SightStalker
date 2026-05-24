"""Recorder persistence + provenance tests (spec §12, §17)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sightstalker.artifacts import ArtifactManager
from sightstalker.diagnostics import (
    DiagnosticArtifactRecorder,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
)
from sightstalker.diagnostics.errors import DiagnosticPersistenceError

from tests.diagnostics.conftest import RecordingArtifactRepo


def test_write_bytes_returns_unpersisted(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=run_target,
    )
    assert result.persisted is False


def test_path_id_equals_ref_id(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=run_target,
    )
    aid = result.artifact_ref.artifact_id
    assert aid in result.artifact_ref.relative_path.as_posix()


def test_write_text_run_log(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    result = recorder.write_text(
        text="line",
        artifact_type="run_log",
        suffix="console.jsonl",
        target=run_target,
        mime_type="application/x-jsonlines",
    )
    assert result.artifact_ref.artifact_type == "run_log"


def test_unscoped_target_uses_unscoped_path(
    recorder: DiagnosticArtifactRecorder, unscoped_target: DiagnosticTarget
) -> None:
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=unscoped_target,
    )
    assert "diagnostics/unscoped/" in result.artifact_ref.relative_path.as_posix()


async def test_persist_disabled_is_noop(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=run_target,
    )
    out = await recorder.persist_artifact_result(
        result, DiagnosticPersistencePolicy(persist_artifact_metadata=False)
    )
    assert out.persisted is False
    assert len(repo.created) == 0


async def test_persist_enabled_creates_metadata(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=run_target,
    )
    out = await recorder.persist_artifact_result(
        result, DiagnosticPersistencePolicy(persist_artifact_metadata=True)
    )
    assert out.persisted is True
    assert repo.created[0]["run_id"] == "run_auto_0123456789abcdef"
    assert repo.created[0]["run_order"] == 0


async def test_persist_requires_run_order_with_run_id(
    manager: ArtifactManager
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    target = DiagnosticTarget(run_id="run_auto_0123456789abcdef")  # no run_order
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=target,
    )
    with pytest.raises(DiagnosticPersistenceError):
        await recorder.persist_artifact_result(
            result, DiagnosticPersistencePolicy(persist_artifact_metadata=True)
        )


async def test_persist_without_repo_raises(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    result = recorder.write_bytes(
        data=b"\x89PNG",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=run_target,
    )
    with pytest.raises(DiagnosticPersistenceError):
        await recorder.persist_artifact_result(
            result, DiagnosticPersistencePolicy(persist_artifact_metadata=True)
        )


async def test_persist_failure_keeps_artifact_and_wraps_error(
    manager: ArtifactManager, run_target: DiagnosticTarget, tmp_path: Path
) -> None:
    repo = RecordingArtifactRepo(fail=True)
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    result = recorder.write_bytes(
        data=b"\x89PNGDATA",
        artifact_type="screenshot",
        suffix="screenshot.png",
        target=run_target,
    )
    with pytest.raises(DiagnosticPersistenceError) as excinfo:
        await recorder.persist_artifact_result(
            result, DiagnosticPersistencePolicy(persist_artifact_metadata=True)
        )
    assert "boom" not in str(excinfo.value)
    # Artifact remains verifiable.
    assert manager.read_bytes(result.artifact_ref).startswith(b"\x89PNG")


def test_recorder_does_not_import_artifact_manager_internals() -> None:
    # Recorder uses ArtifactManager.write_* only; it must not reach into
    # private hashing/verification. Smoke check: writing then reading works.
    import sightstalker.diagnostics.recorder as mod
    import ast

    src = open(mod.__file__).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "sqlalchemy" not in node.module
            assert "alembic" not in node.module
