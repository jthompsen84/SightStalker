"""Security redaction tests for diagnostics (spec §18, §21.7)."""

from __future__ import annotations

from sightstalker.artifacts import ArtifactManager
from sightstalker.diagnostics import (
    ConsoleCaptureService,
    DiagnosticArtifactRecorder,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    HealthService,
    ScreenshotService,
)

from tests.diagnostics.conftest import (
    FakeConsoleMessage,
    FakeNativePage,
    FakePage,
    RecordingArtifactRepo,
    RecordingHealthRepo,
)

_FORBIDDEN_SAMPLES = (
    "raw-token-123",
    "session-cookie-value",
    "Bearer raw-secret",
    "secret-token-abcdef",
)


def _ref_dump(ref: object) -> str:
    return str(ref)


async def test_screenshot_metadata_has_no_payload_bytes(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    service = ScreenshotService(recorder)
    await service.capture(
        FakePage(),
        target=run_target,
        policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True),
    )
    # Persisted metadata is an ArtifactRef: relative path/hash only, no bytes.
    stored = repo.created[0]["ref"]
    assert not hasattr(stored, "data")
    assert b"PNG" not in _ref_dump(stored).encode()


async def test_console_payload_not_in_persisted_metadata(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    native = FakeNativePage()
    page = FakePage(native)
    handle = ConsoleCaptureService(recorder).attach(page, target=run_target)
    native.emit(
        FakeConsoleMessage("log", "Authorization: Bearer secret-token-abcdef")
    )
    await handle.write_artifact(
        policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True)
    )
    stored = repo.created[0]["ref"]
    dump = _ref_dump(stored)
    for sample in _FORBIDDEN_SAMPLES:
        assert sample not in dump


async def test_console_artifact_file_has_no_secrets(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    recorder = DiagnosticArtifactRecorder(manager)
    native = FakeNativePage()
    page = FakePage(native)
    handle = ConsoleCaptureService(recorder).attach(page, target=run_target)
    native.emit(FakeConsoleMessage("log", "token=raw-token-123"))
    native.emit(
        FakeConsoleMessage(
            "error", "x", {"url": "https://x?access_token=raw-token-123"}
        )
    )
    result = await handle.write_artifact()
    text = manager.read_text(result.artifact_ref)
    assert "raw-token-123" not in text


async def test_health_persisted_reason_redacted(
    run_target: DiagnosticTarget,
) -> None:
    repo = RecordingHealthRepo()
    service = HealthService(health_persistence=repo)
    record = service.build_record(
        session_id="sess_alpha_default",
        status="degraded",
        reason="failure access_token=raw-token-123",
    )
    await service.persist_record(record)
    stored = repo.created[0]
    assert "raw-token-123" not in str(stored.reason)


async def test_capture_error_has_no_temp_path(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    recorder = DiagnosticArtifactRecorder(manager)
    service = ScreenshotService(recorder)
    from sightstalker.diagnostics.errors import DiagnosticCaptureError

    import pytest

    page = FakePage(fail=True)
    with pytest.raises(DiagnosticCaptureError) as excinfo:
        await service.capture(page, target=run_target)
    msg = str(excinfo.value)
    # No absolute temp path, no native repr in the public message.
    assert "/tmp" not in msg
    assert "sightstalker-diag-" not in msg
    assert "boom" not in msg
