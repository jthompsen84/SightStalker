"""
sightstalker.diagnostics.console — passive console event capture.

Attaches a listener to the engine-native page (the only place ``native_page``
is used) via the Python Playwright-like surface ``.on("console", cb)`` /
``.remove_listener("console", cb)``. Captured events are redacted immediately
and retained in memory; ``write_artifact`` snapshots the events captured up to
the call and writes a JSONL ``run_log`` artifact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

from sightstalker.diagnostics.errors import DiagnosticCaptureError
from sightstalker.diagnostics.models import (
    ConsoleEventRecord,
    DiagnosticArtifactResult,
    DiagnosticPersistencePolicy,
    DiagnosticTarget,
)
from sightstalker.diagnostics.paths import DiagnosticPathPolicy
from sightstalker.diagnostics.recorder import DiagnosticArtifactRecorder
from sightstalker.diagnostics.redaction import (
    redact_console_location,
    redact_console_text,
)
from sightstalker.engines.base import PageHandle

_CONSOLE_MIME = "application/x-jsonlines"


class NativeConsoleMessage(Protocol):
    """Minimal Python Playwright-like console message surface."""

    @property
    def type(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def location(self) -> Any: ...


class NativeConsolePage(Protocol):
    """Minimal native page surface for console listener management."""

    def on(self, event: str, callback: Any) -> Any: ...

    def remove_listener(self, event: str, callback: Any) -> Any: ...


def _coerce_location(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}  # type: ignore[misc]
    # Playwright location objects expose url/lineNumber/columnNumber.
    out: dict[str, Any] = {}
    for attr in ("url", "lineNumber", "columnNumber"):
        if hasattr(raw, attr):
            out[attr] = getattr(raw, attr)
    return out or None


class ConsoleCaptureHandle:
    """Active console capture; retains redacted events until detached."""

    def __init__(
        self,
        native_page: NativeConsolePage,
        recorder: DiagnosticArtifactRecorder,
        *,
        target: DiagnosticTarget,
    ) -> None:
        self._native_page = native_page
        self._recorder = recorder
        self._target = target
        self._events: list[ConsoleEventRecord] = []
        self._attached = True

        def _listener(message: Any) -> None:
            self._on_console(message)

        self._callback = _listener
        self._native_page.on("console", self._callback)

    def _on_console(self, message: Any) -> None:
        event_type = str(getattr(message, "type", "log"))
        raw_text = str(getattr(message, "text", ""))
        raw_location = getattr(message, "location", None)
        self._events.append(
            ConsoleEventRecord(
                event_type=event_type,
                text_redacted=redact_console_text(raw_text),
                location=redact_console_location(_coerce_location(raw_location)),
                timestamp=datetime.now(timezone.utc),
            )
        )

    @property
    def event_count(self) -> int:
        """Number of events captured so far."""
        return len(self._events)

    def detach(self) -> None:
        """Remove the console listener. Idempotent."""
        if not self._attached:
            return
        try:
            self._native_page.remove_listener("console", self._callback)
        except Exception:
            # Detaching must never raise on the public surface.
            pass
        self._attached = False

    def snapshot(self) -> tuple[ConsoleEventRecord, ...]:
        """Immutable snapshot of events captured up to now."""
        return tuple(self._events)

    async def write_artifact(
        self,
        *,
        filename_suffix: str = "console.jsonl",
        policy: DiagnosticPersistencePolicy | None = None,
    ) -> DiagnosticArtifactResult:
        """Write captured events as a JSONL ``run_log`` artifact.

        Snapshots events captured up to this call; later events are excluded.
        An empty event list produces an empty file (size 0).
        """
        DiagnosticPathPolicy.validate_suffix("console", filename_suffix)
        events = self.snapshot()
        lines: list[str] = []
        for event in events:
            payload = {
                "event_type": event.event_type,
                "text_redacted": event.text_redacted,
                "location": event.location,
                "timestamp": event.timestamp.isoformat(),
            }
            lines.append(
                json.dumps(payload, ensure_ascii=False, sort_keys=True)
            )
        text = "\n".join(lines)

        result = self._recorder.write_text(
            text=text,
            artifact_type="run_log",
            suffix=filename_suffix,
            target=self._target,
            mime_type=_CONSOLE_MIME,
        )
        if policy is not None and policy.persist_artifact_metadata:
            result = await self._recorder.persist_artifact_result(result, policy)
        return result


class ConsoleCaptureService:
    """Passive console capture service."""

    def __init__(self, recorder: DiagnosticArtifactRecorder) -> None:
        self._recorder = recorder

    def attach(
        self, page: PageHandle, *, target: DiagnosticTarget
    ) -> ConsoleCaptureHandle:
        """Attach a console listener to ``page`` and return a capture handle."""
        native = page.native_page
        if not (hasattr(native, "on") and hasattr(native, "remove_listener")):
            raise DiagnosticCaptureError(
                "native page does not support console listener management"
            )
        return ConsoleCaptureHandle(native, self._recorder, target=target)
