"""
sightstalker.diagnostics.tracing — passive trace capture.

``TraceService.start`` begins tracing on an already-open
``BrowserContextHandle`` and returns a ``TraceCaptureHandle`` with a
deterministic lifecycle state machine:

    active -> stopped      (stop succeeds and artifact written)
    active -> failed       (stop_tracing succeeded but artifact write failed)
    active -> discarded    (discard from active: stop_tracing once, delete out)
    stopped/discarded/failed are terminal.

Never closes the context or runtime.
"""

from __future__ import annotations

from sightstalker.diagnostics.errors import DiagnosticCaptureError
from sightstalker.diagnostics.models import (
    DiagnosticArtifactResult,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    TraceOptions,
)
from sightstalker.diagnostics.paths import DiagnosticPathPolicy
from sightstalker.diagnostics.recorder import DiagnosticArtifactRecorder
from sightstalker.diagnostics.tempfiles import hardened_temp_file
from sightstalker.engines.base import BrowserContextHandle

_ACTIVE = "active"
_STOPPED = "stopped"
_DISCARDED = "discarded"
_FAILED = "failed"


class TraceCaptureHandle:
    """Stateful handle controlling one active trace capture."""

    def __init__(
        self,
        context: BrowserContextHandle,
        recorder: DiagnosticArtifactRecorder,
        *,
        target: DiagnosticTarget,
        options: TraceOptions,
    ) -> None:
        self._context = context
        self._recorder = recorder
        self._target = target
        self._options = options
        self._state = _ACTIVE

    @property
    def state(self) -> str:
        """Current lifecycle state."""
        return self._state

    async def stop(
        self, *, policy: DiagnosticPersistencePolicy | None = None
    ) -> DiagnosticArtifactResult:
        """Stop tracing and write the trace artifact.

        Requires ``active``. If stopping succeeds but the artifact write fails,
        the state becomes ``failed`` and tracing is not stopped again.
        """
        if self._state != _ACTIVE:
            raise DiagnosticCaptureError(
                f"cannot stop trace in state '{self._state}'"
            )
        DiagnosticPathPolicy.validate_suffix("trace", self._options.filename_suffix)

        with hardened_temp_file(suffix=".zip") as temp:
            try:
                await self._context.stop_tracing(path=str(temp.path))
            except Exception as exc:
                # Tracing did not stop cleanly; remain failed without retrying.
                self._state = _FAILED
                raise DiagnosticCaptureError(
                    f"trace stop failed: {type(exc).__name__}"
                ) from None

            # From here, tracing IS stopped. Any failure -> failed, no re-stop.
            try:
                data = temp.read_bytes()
                result = self._recorder.write_bytes(
                    data=data,
                    artifact_type="trace",
                    suffix=self._options.filename_suffix,
                    target=self._target,
                    mime_type="application/zip",
                )
            except Exception as exc:
                self._state = _FAILED
                raise DiagnosticCaptureError(
                    f"trace artifact write failed: {type(exc).__name__}"
                ) from None

        if policy is not None and policy.persist_artifact_metadata:
            result = await self._recorder.persist_artifact_result(result, policy)

        self._state = _STOPPED
        return result

    async def discard(self) -> None:
        """Discard the trace. Idempotent.

        From ``active``: stop tracing exactly once (to a temp file) and delete
        the output. From ``stopped``/``discarded``/``failed``: no-op; never
        calls ``stop_tracing`` again.
        """
        if self._state != _ACTIVE:
            # stopped/discarded/failed are terminal; discard is idempotent and
            # must not call stop_tracing again.
            return

        with hardened_temp_file(suffix=".zip") as temp:
            try:
                await self._context.stop_tracing(path=str(temp.path))
            except Exception as exc:
                self._state = _FAILED
                raise DiagnosticCaptureError(
                    f"trace discard failed: {type(exc).__name__}"
                ) from None
            # Temp file is deleted by the context manager on exit.
        self._state = _DISCARDED


class TraceService:
    """Passive trace capture service."""

    def __init__(self, recorder: DiagnosticArtifactRecorder) -> None:
        self._recorder = recorder

    async def start(
        self,
        context: BrowserContextHandle,
        *,
        target: DiagnosticTarget,
        options: TraceOptions | None = None,
    ) -> TraceCaptureHandle:
        """Start tracing on ``context`` and return a capture handle."""
        opts = options or TraceOptions()
        DiagnosticPathPolicy.validate_suffix("trace", opts.filename_suffix)
        try:
            await context.start_tracing(name=opts.name)
        except Exception as exc:
            raise DiagnosticCaptureError(
                f"trace start failed: {type(exc).__name__}"
            ) from None
        return TraceCaptureHandle(
            context, self._recorder, target=target, options=opts
        )
