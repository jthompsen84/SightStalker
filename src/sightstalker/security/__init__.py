"""
sightstalker.security — redaction and security utilities.

Import from this package rather than from submodules directly:

    from sightstalker.security import redact_mapping, redact_log_record
"""

from __future__ import annotations

from sightstalker.security.redaction import (
    SENSITIVE_FIELD_NAMES,
    SENSITIVE_HEADER_NAMES,
    TOKENISH_PATTERN,
    is_sensitive_header,
    is_sensitive_key,
    redact_exception,
    redact_log_record,
    redact_mapping,
    redact_string,
    redact_value,
)

__all__ = [
    "SENSITIVE_FIELD_NAMES",
    "SENSITIVE_HEADER_NAMES",
    "TOKENISH_PATTERN",
    "is_sensitive_header",
    "is_sensitive_key",
    "redact_exception",
    "redact_log_record",
    "redact_mapping",
    "redact_string",
    "redact_value",
]
