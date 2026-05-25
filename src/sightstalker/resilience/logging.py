"""
sightstalker.resilience.logging — redacted, lazy loguru integration.

loguru is imported lazily and configured *only* when ``configure_cli_logging``
is called. Importing this module (or the CLI) never configures loguru or adds
an active sink.

Configuration rules:
- idempotent: repeated calls remove prior sinks and never accumulate;
- JSON non-verbose: logging suppressed (no sink);
- JSON verbose: logs to stderr only;
- human verbose: sanitized logs to stderr;
- never logs to stdout in JSON mode;
- all sinks use ``backtrace=False`` and ``diagnose=False``;
- every record is passed through :func:`redact_cli_log_record` before output.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from sightstalker.resilience.operator_redaction import sanitize_operator_message
from sightstalker.security.redaction import redact_mapping

# Tracks the sink id we installed so repeated configuration is idempotent.
_installed_sink_id: int | None = None


def redact_cli_log_record(record: dict[str, Any]) -> None:
    """Sanitize a loguru log record in place; returns ``None``.

    Builds on the accepted structural redaction and additionally applies
    operator message sanitization (control-char stripping, embedded-URL
    credential redaction). Exception text is reduced to the class name so no
    raw cause/traceback content reaches a sink.
    """
    message = record.get("message")
    if isinstance(message, str):
        record["message"] = sanitize_operator_message(message)

    extra = record.get("extra")
    if isinstance(extra, Mapping):
        record["extra"] = redact_mapping(cast("Mapping[str, Any]", extra))

    # Never let exception text/traceback leak through the record.
    exception = record.get("exception")
    if exception is not None:
        record["exception"] = None


def configure_cli_logging(
    *,
    verbose: bool = False,
    json_output: bool = False,
) -> None:
    """Configure loguru for a CLI command (idempotent, redacted, stderr-only).

    No sink is installed when ``json_output`` and not ``verbose`` (logs
    suppressed). Otherwise a single sanitized stderr sink is installed with
    ``backtrace=False`` / ``diagnose=False``. Safe to call repeatedly.

    Redaction is enforced by patching the logger with
    :func:`redact_cli_log_record` (which sanitizes ``message``/``extra`` and
    drops ``exception``) before a static, traceback-free format is applied.
    """
    import sys

    from loguru import logger

    global _installed_sink_id

    # Always start from a clean slate so we never accumulate sinks and never
    # leave loguru's default stderr sink (which would bypass our redaction).
    logger.remove()
    _installed_sink_id = None

    # JSON, non-verbose: logs are fully suppressed.
    if json_output and not verbose:
        return

    # Install a process-global patcher so every record (regardless of which
    # logger reference emitted it) is sanitized before formatting. ``patch()``
    # only affects the bound logger it returns, so ``configure(patcher=...)`` is
    # required for global redaction. loguru types the patcher over its private
    # ``Record`` TypedDict; our hook accepts a plain mutable mapping.
    logger.configure(patcher=cast("Any", redact_cli_log_record))
    level = "DEBUG" if verbose else "INFO"
    _installed_sink_id = logger.add(
        sys.stderr,
        level=level,
        format="{level}: {message}",
        backtrace=False,
        diagnose=False,
        colorize=False,
    )


# Backwards/compat alias — routes to the canonical record redactor.
def redact_log_record(record: dict[str, Any]) -> None:
    """Deprecated alias for :func:`redact_cli_log_record`."""
    redact_cli_log_record(record)


__all__ = [
    "configure_cli_logging",
    "redact_cli_log_record",
    "redact_log_record",
]
