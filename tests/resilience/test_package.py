"""Package-level tests for the resilience layer."""

from __future__ import annotations

import sightstalker
import sightstalker.resilience as resilience


def test_version_is_0_4_5() -> None:
    assert sightstalker.__version__ == "0.4.5"


def test_resilience_public_exports_resolve() -> None:
    for name in resilience.__all__:
        assert hasattr(resilience, name), f"missing export: {name}"


def test_required_public_names_present() -> None:
    required = {
        "SightStalkerError",
        "ResilienceError",
        "UsageError",
        "ConfigurationError",
        "SecurityRefusal",
        "BrowserRuntimeError",
        "PersistenceFailure",
        "DiagnosticFailure",
        "TimeoutFailure",
        "ErrorKind",
        "ErrorSeverity",
        "Recoverability",
        "OperatorError",
        "ResiliencePolicy",
        "TimeoutPolicy",
        "RetryPolicy",
        "OperationSafety",
        "classify_exception",
        "operator_error_from_message",
        "configure_cli_logging",
        "redact_cli_log_record",
        "retry_async",
        "retry_sync",
        "exception_to_operator_error",
        "error_to_operator_error",
        "sanitize_operator_message",
        "sanitize_title_for_operator",
        "sanitize_url_for_operator_metadata",
    }
    missing = {n for n in required if not hasattr(resilience, n)}
    assert missing == set(), f"missing required exports: {missing}"


def test_resilience_package_importable() -> None:
    import importlib

    for sub in (
        "classification",
        "errors",
        "logging",
        "models",
        "operator",
        "operator_redaction",
        "retry",
        "timeouts",
    ):
        module = importlib.import_module(f"sightstalker.resilience.{sub}")
        assert module is not None
