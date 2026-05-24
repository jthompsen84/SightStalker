"""Trace service + state machine tests (spec §14)."""

from __future__ import annotations

import pytest

from sightstalker.artifacts import ArtifactManager
from sightstalker.diagnostics import (
    DiagnosticArtifactRecorder,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    TraceService,
)
from sightstalker.diagnostics.errors import DiagnosticCaptureError

from tests.diagnostics.conftest import FakeContext, RecordingArtifactRepo


async def test_start_returns_active_handle(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    assert handle.state == "active"
    assert ctx.start_calls == 1


async def test_stop_writes_trace_artifact(
    recorder: DiagnosticArtifactRecorder,
    manager: ArtifactManager,
    run_target: DiagnosticTarget,
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    result = await handle.stop()
    assert handle.state == "stopped"
    assert result.artifact_ref.artifact_type == "trace"
    assert manager.read_bytes(result.artifact_ref).startswith(b"PK")


async def test_stop_from_non_active_raises(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    await handle.stop()
    with pytest.raises(DiagnosticCaptureError):
        await handle.stop()


async def test_second_stop_raises(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    await handle.stop()
    with pytest.raises(DiagnosticCaptureError):
        await handle.stop()
    # stop_tracing called exactly once.
    assert ctx.stop_calls == 1


async def test_discard_from_active_stops_once(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    await handle.discard()
    assert handle.state == "discarded"
    assert ctx.stop_calls == 1


async def test_discard_idempotent(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    await handle.discard()
    await handle.discard()
    await handle.discard()
    assert handle.state == "discarded"
    assert ctx.stop_calls == 1


async def test_discard_after_stop_does_not_restop(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    await handle.stop()
    await handle.discard()
    assert handle.state == "stopped"
    assert ctx.stop_calls == 1


async def test_stop_native_failure_sets_failed(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext(fail_stop=True)
    handle = await TraceService(recorder).start(ctx, target=run_target)
    with pytest.raises(DiagnosticCaptureError):
        await handle.stop()
    assert handle.state == "failed"


async def test_write_failure_after_stop_sets_failed_no_restop(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    # Force an artifact-write failure by making the recorder's path collide.
    ctx = FakeContext()

    class BoomRecorder(DiagnosticArtifactRecorder):
        def write_bytes(self, **kwargs):  # type: ignore[override]
            raise RuntimeError("write boom")

    recorder = BoomRecorder(manager)
    handle = await TraceService(recorder).start(ctx, target=run_target)
    with pytest.raises(DiagnosticCaptureError):
        await handle.stop()
    assert handle.state == "failed"
    assert ctx.stop_calls == 1
    # discard must not call stop_tracing again.
    await handle.discard()
    assert ctx.stop_calls == 1


async def test_start_native_failure_raises(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    ctx = FakeContext(fail_start=True)
    with pytest.raises(DiagnosticCaptureError):
        await TraceService(recorder).start(ctx, target=run_target)


async def test_stop_with_persistence(
    manager: ArtifactManager, run_target: DiagnosticTarget
) -> None:
    repo = RecordingArtifactRepo()
    recorder = DiagnosticArtifactRecorder(manager, artifact_persistence=repo)
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    result = await handle.stop(
        policy=DiagnosticPersistencePolicy(persist_artifact_metadata=True)
    )
    assert result.persisted is True
    assert len(repo.created) == 1


async def test_no_context_close_methods_called(
    recorder: DiagnosticArtifactRecorder, run_target: DiagnosticTarget
) -> None:
    # FakeContext has no close(); a call would AttributeError. Exercise full
    # lifecycle to prove no close is attempted.
    ctx = FakeContext()
    handle = await TraceService(recorder).start(ctx, target=run_target)
    await handle.stop()
    assert not hasattr(ctx, "closed")
