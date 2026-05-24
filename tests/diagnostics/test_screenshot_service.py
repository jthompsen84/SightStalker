"""Screenshot service tests (spec §13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sightstalker.artifacts import ArtifactManager
from sightstalker.diagnostics import (
    DiagnosticArtifactRecorder,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    ScreenshotOptions,
    ScreenshotService,
)
from sightstalker.diagnostics.errors import (
    DiagnosticCaptureError,
    DiagnosticPersistenceError,
)

from tests.diagnostics.conftest import FakePage, RecordingArtifactRepo


async def test_capture_writes_artifact(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    service = ScreenshotService(recorder)
    page = FakePage()
    result = await service.capture(page, target=run_target)
    assert result.artifact_ref.artifact_type == "screenshot"
    assert result.persisted is False
    # Bytes round-trip through ArtifactManager.
    assert manager.read_bytes(result.artifact_ref).startswith(b"\x89PNG")


async def test_path_id_equals_ref_id(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    result = await service.capture(FakePage(), target=run_target)
    aid = result.artifact_ref.artifact_id
    assert aid in result.artifact_ref.relative_path.as_posix()


async def test_options_passed_to_native(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    page = FakePage()
    await service.capture(
        page,
        target=run_target,
        options=ScreenshotOptions(full_page=True, timeout_ms=5000),
    )
    assert page.screenshot_calls[0]["full_page"] is True
    assert page.screenshot_calls[0]["timeout_ms"] == 5000


async def test_final_path_not_passed_to_native(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    page = FakePage()
    result = await service.capture(page, target=run_target)
    native_path = page.screenshot_calls[0]["path"]
    # The native writer received a temp path, not the final artifact path.
    assert result.artifact_ref.relative_path.as_posix() not in native_path
    assert "diagnostics/runs" not in native_path


async def test_temp_file_cleaned_on_success(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    page = FakePage()
    await service.capture(page, target=run_target)
    temp_path = Path(page.screenshot_calls[0]["path"])
    assert not temp_path.exists()


async def test_temp_file_cleaned_on_failure(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    page = FakePage(fail=True)
    with pytest.raises(DiagnosticCaptureError):
        await service.capture(page, target=run_target)
    temp_path = Path(page.screenshot_calls[0]["path"])
    assert not temp_path.exists()


async def test_capture_failure_message_no_native_repr(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    with pytest.raises(DiagnosticCaptureError) as excinfo:
        await service.capture(FakePage(fail=True), target=run_target)
    assert "boom" not in str(excinfo.value)


async def test_capture_with_persistence(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    service = ScreenshotService(recorder)
    result = await service.capture(
        FakePage(),
        target=run_target,
        policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True),
    )
    assert result.persisted is True
    assert len(repo.created) == 1
    assert repo.created[0]["run_order"] == 0


async def test_persistence_without_repo_raises(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    service = ScreenshotService(recorder)
    with pytest.raises(DiagnosticPersistenceError):
        await service.capture(
            FakePage(),
            target=run_target,
            policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True),
        )


async def test_orphan_artifact_remains_after_persistence_failure(
    manager: ArtifactManager, run_target: DiagnosticTarget, tmp_path: Path
) -> None:
    repo = RecordingArtifactRepo(fail=True)
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    service = ScreenshotService(recorder)
    with pytest.raises(DiagnosticPersistenceError):
        await service.capture(
            FakePage(),
            target=run_target,
            policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True),
        )
    # The artifact write happened before persistence; the file must remain and
    # be independently verifiable. The manager fixture uses tmp_path/"data".
    run_dir = (
        tmp_path / "data" / "diagnostics" / "runs" / "run_auto_0123456789abcdef"
    )
    files = list(run_dir.glob("*.png"))
    assert len(files) == 1
    assert files[0].read_bytes().startswith(b"\x89PNG")
