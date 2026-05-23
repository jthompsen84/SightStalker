"""
sightstalker.security.redaction — structural redaction utilities.

These utilities are the enforcement point for the project's security boundary.
They must be used at all log emission sites, exception formatting points, and
before any external serialization of potentially sensitive data.

Rules enforced here:
- Cookies, authorization headers, proxy credentials, tokens, passwords,
  storage state, and API keys are always redacted.
- SecretStr and SecretBytes values are always redacted.
- Nested structures (dicts, lists) are recursively sanitized.
- Exception strings are sanitized without including tracebacks or locals.
- redact_log_record() is loguru-compatible: mutates in place, returns None.

Do not add loguru as a dependency in this module. The hook is compatible
with loguru's logger.patch() API but must not import it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from pydantic import SecretBytes, SecretStr

# ---------------------------------------------------------------------------
# Sensitive field / header sets
# ---------------------------------------------------------------------------

SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "cookie",
        "cookies",
        "authorization",
        "proxy_authorization",
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "secret",
        "client_secret",
        "password",
        "passphrase",
        "api_key",
        "apikey",
        "private_key",
        "storage_state",
        "local_storage",
        "session_storage",
    }
)

SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
    }
)

# ---------------------------------------------------------------------------
# Token-like inline pattern
#
# Matches key=value / key: value / key="value" / key='value' patterns for
# known sensitive key names appearing inside log strings or exception messages.
# ---------------------------------------------------------------------------

TOKENISH_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b("
    r"access_token|refresh_token|id_token|client_secret|api_key|apikey"
    r"|password|passphrase|private_key|secret|token"
    r")['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_.~+/=-]{4,}['\"]?",
    re.ASCII,
)


# ---------------------------------------------------------------------------
# Key / header classification
# ---------------------------------------------------------------------------


def is_sensitive_key(key: str) -> bool:
    """Return True if the key name matches a known sensitive field name."""
    normalized = key.strip().lower().replace("-", "_")
    return normalized in SENSITIVE_FIELD_NAMES


def is_sensitive_header(key: str) -> bool:
    """Return True if the header name matches a known sensitive header."""
    normalized = key.strip().lower()
    return normalized in SENSITIVE_HEADER_NAMES


# ---------------------------------------------------------------------------
# String-level redaction
# ---------------------------------------------------------------------------


def redact_string(value: str) -> str:
    """
    Redact token-like key=value pairs from an arbitrary string.

    Used for sanitizing log messages and exception strings.
    Does not guarantee exhaustive sanitization of all possible encodings.
    """
    return TOKENISH_PATTERN.sub(
        lambda m: f"{m.group(1)}=<redacted>",
        value,
    )


# ---------------------------------------------------------------------------
# Value-level redaction
# ---------------------------------------------------------------------------


def redact_value(value: Any) -> Any:
    """
    Recursively redact a single value.

    - SecretStr / SecretBytes → "<redacted>"
    - str → redact_string(value)
    - Mapping → redact_mapping(value)
    - non-bytes Sequence → [redact_value(item) for item in value]
    - anything else → returned as-is
    """
    if isinstance(value, SecretStr | SecretBytes):
        return "<redacted>"
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, Mapping):
        return redact_mapping(cast("Mapping[str, Any]", value))
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [redact_value(item) for item in cast("Sequence[Any]", value)]
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """
    Return a copy of a mapping with all sensitive keys and nested values
    recursively redacted.

    Sensitive keys are replaced with the literal string "<redacted>".
    Non-sensitive keys have their values recursively processed by redact_value.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if is_sensitive_key(key) or is_sensitive_header(key):
            result[key] = "<redacted>"
        else:
            result[key] = redact_value(value)
    return result


# ---------------------------------------------------------------------------
# Exception redaction
# ---------------------------------------------------------------------------


def redact_exception(exc: BaseException) -> str:
    """
    Convert an exception to a log-safe string.

    Includes the exception class name and a sanitized message string.
    Does not include traceback, locals, or raw request payloads.

    Usage:
        logger.error(redact_exception(exc))
    """
    raw = f"{exc.__class__.__name__}: {exc}"
    return redact_string(raw)


# ---------------------------------------------------------------------------
# Loguru-compatible log record hook
# ---------------------------------------------------------------------------


def redact_log_record(record: dict[str, Any]) -> None:
    """
    Sanitize a loguru log record in place.

    This function is designed for use with loguru's logger.patch() API:

        from loguru import logger
        logger = logger.patch(redact_log_record)

    Semantics:
    - Mutates record["message"] if present.
    - Mutates record["extra"] if it is a mapping.
    - Returns None (in-place mutation model; do not use the return value).
    - Does not import loguru; the hook is compatible but not dependent.
    """
    message = record.get("message")
    if isinstance(message, str):
        record["message"] = redact_string(message)

    extra = record.get("extra")
    if isinstance(extra, Mapping):
        record["extra"] = redact_mapping(cast("Mapping[str, Any]", extra))
