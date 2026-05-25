"""
sightstalker.resilience — project-wide failure taxonomy, timeout/retry policy,
operator error formatting, and redacted logging integration.

Importing this package may import tenacity and loguru lazily through its
submodules, but it must NOT configure loguru or add an active sink, and it must
not import any browser package, web framework, or the CLI app/main modules.
"""

from __future__ import annotations

from sightstalker.resilience.classification import (
    classify_exception,
    operator_error_from_message,
)
from sightstalker.resilience.errors import (
    BrowserRuntimeError,
    ConfigurationError,
    DiagnosticFailure,
    PersistenceFailure,
    ResilienceError,
    SecurityRefusal,
    SightStalkerError,
    TimeoutFailure,
    UsageError,
)
from sightstalker.resilience.logging import (
    configure_cli_logging,
    redact_cli_log_record,
)
from sightstalker.resilience.models import (
    ErrorKind,
    ErrorSeverity,
    OperatorError,
    Recoverability,
    ResiliencePolicy,
)
from sightstalker.resilience.operator import (
    error_to_operator_error,
    exception_to_operator_error,
    operator_error_to_human,
    operator_error_to_json,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_operator_details,
    sanitize_operator_message,
    sanitize_title_for_operator,
    sanitize_url_for_operator_metadata,
)
from sightstalker.resilience.retry import (
    OperationSafety,
    RetryPolicy,
    retry_async,
    retry_sync,
)
from sightstalker.resilience.timeouts import TimeoutPolicy

__all__ = [
    "BrowserRuntimeError",
    "ConfigurationError",
    "DiagnosticFailure",
    "ErrorKind",
    "ErrorSeverity",
    "OperationSafety",
    "OperatorError",
    "PersistenceFailure",
    "Recoverability",
    "ResilienceError",
    "ResiliencePolicy",
    "RetryPolicy",
    "SecurityRefusal",
    "SightStalkerError",
    "TimeoutFailure",
    "TimeoutPolicy",
    "UsageError",
    "classify_exception",
    "configure_cli_logging",
    "error_to_operator_error",
    "exception_to_operator_error",
    "operator_error_from_message",
    "operator_error_to_human",
    "operator_error_to_json",
    "redact_cli_log_record",
    "retry_async",
    "retry_sync",
    "sanitize_operator_details",
    "sanitize_operator_message",
    "sanitize_title_for_operator",
    "sanitize_url_for_operator_metadata",
]
