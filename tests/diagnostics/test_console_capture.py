"""Console capture service tests (spec §15)."""

from __future__ import annotations

import json

import pytest

from sightstalker.artifacts import ArtifactManager
from sightstalker.diagnostics import (
    ConsoleCaptureHandle,
    ConsoleCaptureService,
    DiagnosticArtifactRecorder,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
)
from sightstalker.diagnostics.errors import DiagnosticCaptureError

from tests.diagnostics.conftest import (
    FakeConsoleMessage,
    FakeNativePage,
    FakePage,
    RecordingArtifactRepo,
)


def _attach(
    recorder: DiagnosticArtifactRecorder, target: DiagnosticTarget
) -> tuple[FakeNativePage, ConsoleCaptureHandle]:
    native = FakeNativePage()
    page = FakePage(native)
    handle = ConsoleCaptureService(recorder).attach(page, target=target)
    return native, handle


async def test_attach_uses_on_listener(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    native, handle = _attach(recorder, run_target)
    native.emit(FakeConsoleMessage("log", "hello"))
    assert handle.event_count == 1


async def test_detach_uses_remove_listener(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    native, handle = _attach(recorder, run_target)
    handle.detach()
    assert native.removed is True
    # Events after detach are not captured.
    native.emit(FakeConsoleMessage("log", "after"))
    assert handle.event_count == 0


async def test_detach_idempotent(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    _native, handle = _attach(recorder, run_target)
    handle.detach()
    handle.detach()  # no raise


async def test_console_text_redacted(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    native, handle = _attach(recorder, run_target)
    native.emit(
        FakeConsoleMessage("log", "Authorization: Bearer secret-token-abcdef")
    )
    result = await handle.write_artifact()
    text = manager.read_text(result.artifact_ref)
    assert "secret-token-abcdef" not in text


async def test_console_location_redacted(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    native, handle = _attach(recorder, run_target)
    native.emit(
        FakeConsoleMessage(
            "error",
            "boom",
            {"url": "https://x/cb?access_token=raw-token-123", "lineNumber": 3},
        )
    )
    result = await handle.write_artifact()
    text = manager.read_text(result.artifact_ref)
    assert "raw-token-123" not in text


async def test_console_artifact_is_run_log_jsonl(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    native, handle = _attach(recorder, run_target)
    native.emit(FakeConsoleMessage("log", "one"))
    native.emit(FakeConsoleMessage("warning", "two"))
    result = await handle.write_artifact()
    assert result.artifact_ref.artifact_type == "run_log"
    assert result.artifact_ref.mime_type == "application/x-jsonlines"
    text = manager.read_text(result.artifact_ref)
    lines = text.split("\n")
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert "event_type" in parsed
        assert "text_redacted" in parsed
        assert "timestamp" in parsed


async def test_empty_console_produces_empty_file(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    _native, handle = _attach(recorder, run_target)
    result = await handle.write_artifact()
    assert result.artifact_ref.size_bytes == 0
    assert manager.read_bytes(result.artifact_ref) == b""


async def test_write_artifact_snapshots_up_to_call(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    native, handle = _attach(recorder, run_target)
    native.emit(FakeConsoleMessage("log", "before"))
    result = await handle.write_artifact()
    text = manager.read_text(result.artifact_ref)
    assert text.count("\n") == 0  # exactly one line, no trailing newline
    # Later events are excluded from the already-written artifact.
    native.emit(FakeConsoleMessage("log", "after"))
    assert handle.event_count == 2
    assert "after" not in text


async def test_attach_rejects_page_without_listeners(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    class NoListenerNative:
        pass

    page = FakePage(NoListenerNative())
    with pytest.raises(DiagnosticCaptureError):
        ConsoleCaptureService(recorder).attach(page, target=run_target)


async def test_console_with_persistence(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    native = FakeNativePage()
    page = FakePage(native)
    handle = ConsoleCaptureService(recorder).attach(page, target=run_target)
    native.emit(FakeConsoleMessage("log", "x"))
    result = await handle.write_artifact(
        policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True)
    )
    assert result.persisted is True
    assert len(repo.created) == 1
