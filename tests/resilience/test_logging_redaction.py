"""Logging tests: lazy loguru config, idempotency, redaction, no leaks."""

from __future__ import annotations

import subprocess
import sys

from sightstalker.resilience.logging import (
    configure_cli_logging,
    redact_cli_log_record,
)


def _run_probe(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_importing_resilience_does_not_configure_loguru() -> None:
    probe = (
        "import sys, sightstalker.resilience;"
        "print('loguru' in sys.modules);"
        "sys.exit(1 if 'loguru' in sys.modules else 0)"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stdout + result.stderr


def test_importing_cli_does_not_configure_loguru() -> None:
    probe = (
        "import sys, sightstalker.cli.main;"
        "print('loguru' in sys.modules);"
        "sys.exit(1 if 'loguru' in sys.modules else 0)"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, result.stdout + result.stderr


def _handler_count() -> int:
    from typing import Any, cast

    from loguru import logger

    handlers = cast("dict[int, Any]", logger._core.handlers)  # type: ignore[attr-defined]
    return len(handlers)


def test_json_non_verbose_suppresses_logs() -> None:
    configure_cli_logging(json_output=True, verbose=False)
    assert _handler_count() == 0


def test_json_verbose_installs_single_sink() -> None:
    configure_cli_logging(json_output=True, verbose=True)
    assert _handler_count() == 1
    configure_cli_logging(json_output=True, verbose=False)  # cleanup


def test_human_verbose_installs_single_sink() -> None:
    configure_cli_logging(json_output=False, verbose=True)
    assert _handler_count() == 1
    configure_cli_logging(json_output=True, verbose=False)  # cleanup


def test_repeated_configure_does_not_accumulate_sinks() -> None:
    configure_cli_logging(json_output=False, verbose=False)
    configure_cli_logging(json_output=False, verbose=False)
    configure_cli_logging(json_output=False, verbose=False)
    assert _handler_count() == 1
    configure_cli_logging(json_output=True, verbose=False)  # cleanup


def test_sinks_disable_backtrace_and_diagnose() -> None:
    from typing import Any, cast

    from loguru import logger

    configure_cli_logging(json_output=False, verbose=True)
    handlers = cast(
        "dict[int, Any]",
        logger._core.handlers,  # type: ignore[attr-defined]
    )
    for handler in handlers.values():
        # backtrace/diagnose are stored on the handler's exception formatter.
        formatter = handler._exception_formatter
        assert formatter._backtrace is False
        assert formatter._diagnose is False
    configure_cli_logging(json_output=True, verbose=False)  # cleanup


def test_record_redactor_returns_none_and_mutates() -> None:
    record: dict[str, object] = {
        "message": "auth access_token=raw-token-123",
        "extra": {"password": "db-password-xyz", "ok": "fine"},
        "exception": "should be dropped",
    }
    result = redact_cli_log_record(record)
    assert result is None
    assert "raw-token-123" not in str(record["message"])
    assert "db-password-xyz" not in str(record["extra"])
    assert record["exception"] is None


def test_emitted_logs_redact_secrets() -> None:
    # Configure a real stderr sink and emit; capture via subprocess.
    probe = (
        "import sys;"
        "from sightstalker.resilience.logging import configure_cli_logging;"
        "configure_cli_logging(json_output=False, verbose=True);"
        "from loguru import logger;"
        "logger.info('token=raw-token-123 cookie=session-cookie-value');"
        "logger.info('db sqlite+aiosqlite://user:secret@host');"
    )
    result = _run_probe(probe)
    combined = result.stdout + result.stderr
    for secret in ("raw-token-123", "session-cookie-value", "user:secret"):
        assert secret not in combined


def test_no_stdout_logs_in_json_mode() -> None:
    probe = (
        "from sightstalker.resilience.logging import configure_cli_logging;"
        "configure_cli_logging(json_output=True, verbose=False);"
        "from loguru import logger;"
        "logger.info('should be suppressed entirely')"
    )
    result = _run_probe(probe)
    assert result.stdout == ""
    assert "should be suppressed" not in result.stderr


def test_cause_exception_secret_not_logged() -> None:
    probe = (
        "from sightstalker.resilience.logging import configure_cli_logging;"
        "configure_cli_logging(json_output=False, verbose=True);"
        "from loguru import logger;"
        "try:\n"
        "    raise ValueError('inner token=raw-token-123')\n"
        "except ValueError:\n"
        "    logger.exception('outer failure')\n"
    )
    result = _run_probe(probe)
    combined = result.stdout + result.stderr
    assert "raw-token-123" not in combined
