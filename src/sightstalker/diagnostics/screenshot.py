"""
sightstalker.diagnostics.screenshot — passive screenshot capture.

Captures a screenshot from an already-open ``PageHandle`` into a hardened temp
file, reads the bytes, and writes the final artifact through the recorder /
``ArtifactManager``. It never passes the final artifact path to the browser
writer, never navigates, and never closes the page/context/runtime.
"""

from __future__ import annotations

from sightstalker.diagnostics.errors import DiagnosticCaptureError
from sightstalker.diagnostics.models import (
    DiagnosticArtifactResult,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
    ScreenshotOptions,
)
from sightstalker.diagnostics.paths import DiagnosticPathPolicy
from sightstalker.diagnostics.recorder import DiagnosticArtifactRecorder
from sightstalker.diagnostics.tempfiles import hardened_temp_file
from sightstalker.engines.base import PageHandle


class ScreenshotService:
    """Passive screenshot capture into hardened artifacts."""

    def __init__(self, recorder: DiagnosticArtifactRecorder) -> None:
        self._recorder = recorder

    async def capture(
        self,
        page: PageHandle,
        *,
        target: DiagnosticTarget,
        options: ScreenshotOptions | None = None,
        policy: DiagnosticPersistencePolicy | None = None,
    ) -> DiagnosticArtifactResult:
        """Capture a screenshot and write it as a diagnostic artifact."""
        opts = options or ScreenshotOptions()
        # Validate the suffix up front through the single path authority.
        DiagnosticPathPolicy.validate_suffix("screenshot", opts.filename_suffix)

        with hardened_temp_file(suffix=".png") as temp:
            try:
                await page.screenshot(
                    path=str(temp.path),
                    full_page=opts.full_page,
                    timeout_ms=opts.timeout_ms,
                )
            except Exception as exc:
                raise DiagnosticCaptureError(
                    f"screenshot capture failed: {type(exc).__name__}"
                ) from None
            data = temp.read_bytes()

        result = self._recorder.write_bytes(
            data=data,
            artifact_type="screenshot",
            suffix=opts.filename_suffix,
            target=target,
            mime_type="image/png",
        )

        if policy is not None and policy.persist_artifact_metadata:
            result = await self._recorder.persist_artifact_result(result, policy)
        return result
