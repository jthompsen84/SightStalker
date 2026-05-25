"""
sightstalker.resilience.operator_redaction — dependency-light sanitizers.

This module is the canonical home for turning untrusted/sensitive operator
strings (messages, URLs, titles, detail mappings) into output-, log-, and
persistence-safe forms. It builds only on ``sightstalker.security.redaction``
and the standard library.

Hard rules:
- no Typer / Rich imports
- no CLI app/main imports
- no tenacity / loguru / SQLAlchemy imports
- ``data:`` URL output may show the scheme/media-type prefix but never the body
- URL query/fragment sensitive values are redacted; userinfo is stripped

The CLI (``sightstalker.cli.redaction``) and resilience logging both consume
these helpers so there is exactly one redaction implementation.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sightstalker.models import JsonObject
from sightstalker.security.redaction import (
    is_sensitive_key,
    redact_mapping,
    redact_string,
)

# Output caps (kept identical to the accepted CLI values).
TITLE_MAX_CHARS = 512
MESSAGE_MAX_CHARS = 2000

_DATA_HTML_PREFIX = "data:text/html"
_REDACTED = "<redacted>"

# ``Authorization: Bearer <token>`` / ``Basic <token>`` style secrets that have
# no ``key=value`` shape and so are missed by the structural token redactor.
_AUTH_SCHEME_PATTERN = re.compile(
    r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{3,}",
)

# Sensitive ``key=value`` / ``key: value`` pairs whose key names are NOT in the
# base ``redact_string`` token list (notably ``cookie`` and auth headers).
_OPERATOR_KV_PATTERN = re.compile(
    r"(?i)\b("
    r"cookie|set[_-]?cookie|authorization|proxy[_-]?authorization"
    r"|x[_-]api[_-]key|session"
    r")\s*[:=]\s*['\"]?[^'\"\s,}]+",
)

# Substrings that mark a query/fragment key as sensitive for display.
_SENSITIVE_QUERY_SUBSTRINGS = (
    "token",
    "secret",
    "key",
    "password",
    "passwd",
    "pwd",
    "auth",
    "session",
    "sid",
    "cookie",
    "credential",
    "access",
    "refresh",
    "bearer",
)


def _strip_control_chars(value: str) -> str:
    """Remove C0/C1 control characters and DEL from ``value``."""
    return "".join(
        ch for ch in value if not (ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F)
    )


def _is_sensitive_query_key(key: str) -> bool:
    normalized = key.strip().lower()
    if is_sensitive_key(normalized):
        return True
    return any(token in normalized for token in _SENSITIVE_QUERY_SUBSTRINGS)


def _looks_tokenlike(value: str) -> bool:
    """Heuristic for long, opaque token-like values."""
    if len(value) < 20:
        return False
    return all(ch.isalnum() or ch in "_-./+=~" for ch in value)


def _redact_query_string(query: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    redacted: list[tuple[str, str]] = []
    for key, value in pairs:
        if _is_sensitive_query_key(key) or _looks_tokenlike(value):
            redacted.append((key, _REDACTED))
        else:
            redacted.append((key, value))
    return urlencode(redacted)


def sanitize_operator_message(value: object) -> str:
    """Return a stdout/stderr/JSON/log-safe sanitized string for ``value``.

    Strips control characters, redacts token-like ``key=value`` pairs and any
    embedded URL credentials, and caps length. Never raises.
    """
    text = value if isinstance(value, str) else str(value)
    text = _strip_control_chars(text)
    text = _redact_embedded_urls(text)
    text = _AUTH_SCHEME_PATTERN.sub(lambda m: f"{m.group(1)} {_REDACTED}", text)
    text = _OPERATOR_KV_PATTERN.sub(lambda m: f"{m.group(1)}={_REDACTED}", text)
    text = redact_string(text)
    if len(text) > MESSAGE_MAX_CHARS:
        text = text[:MESSAGE_MAX_CHARS] + "..."
    return text


def _redact_embedded_urls(text: str) -> str:
    """Redact userinfo in any ``scheme://user:pass@host`` substring.

    ``redact_string`` only catches ``key=value`` token pairs, so a bare DB URL
    like ``sqlite+aiosqlite://user:secret@host`` would otherwise survive. This
    collapses any ``//<userinfo>@`` to ``//<redacted>@`` token-by-token.
    """
    out: list[str] = []
    for token in text.split(" "):
        if "://" in token and "@" in token:
            scheme, _, rest = token.partition("://")
            if "@" in rest:
                _userinfo, _, host_part = rest.rpartition("@")
                out.append(f"{scheme}://{_REDACTED}@{host_part}")
                continue
        out.append(token)
    return " ".join(out)


def sanitize_url_for_operator_metadata(url: str) -> str:
    """Return an output/persistence-safe form of ``url``.

    ``about:blank`` and ``data:text/html`` forms return their already-safe
    shapes (the ``data:`` body is never shown). For http/https URLs, userinfo
    is stripped and sensitive query/fragment values are redacted.
    """
    lowered = url.strip().lower()
    if lowered == "about:blank":
        return "about:blank"
    if lowered.startswith(_DATA_HTML_PREFIX):
        return f"{_DATA_HTML_PREFIX},{_REDACTED}"
    if lowered.startswith("data:"):
        # Any other data: form: keep only an opaque scheme marker.
        return f"data:{_REDACTED}"

    parts = urlsplit(url)
    if parts.scheme == "":
        return redact_string(_strip_control_chars(url))

    netloc = parts.hostname or ""
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"

    query = _redact_query_string(parts.query)
    fragment = _redact_query_string(parts.fragment) if parts.fragment else ""

    rebuilt = urlunsplit((parts.scheme, netloc, parts.path, query, fragment))
    return redact_string(rebuilt)


def sanitize_title_for_operator(title: str | None) -> str | None:
    """Make a target-controlled page title safe for output/persistence."""
    if title is None:
        return None
    cleaned = _strip_control_chars(title)
    cleaned = redact_string(cleaned)
    if len(cleaned) > TITLE_MAX_CHARS:
        cleaned = cleaned[:TITLE_MAX_CHARS]
    return cleaned


def sanitize_operator_details(details: JsonObject | None) -> JsonObject | None:
    """Recursively sanitize a details mapping for safe output/logging."""
    if details is None:
        return None
    # ``redact_mapping`` replaces sensitive keys wholesale and recursively
    # redacts string values via ``redact_string``; additionally collapse any
    # embedded URL credentials in leaf strings.
    redacted = redact_mapping(details)
    return _sanitize_leaf_urls(redacted)


def _sanitize_leaf_urls(value: JsonObject) -> JsonObject:
    out: JsonObject = {}
    for key, item in value.items():
        out[key] = _sanitize_detail_value(item)
    return out


def _sanitize_detail_value(item: object) -> object:
    if isinstance(item, str):
        return _redact_embedded_urls(item)
    if isinstance(item, dict):
        typed: JsonObject = {str(k): v for k, v in item.items()}  # type: ignore[misc]
        return _sanitize_leaf_urls(typed)
    if isinstance(item, list):
        elements: list[object] = list(item)  # type: ignore[misc]
        return [_sanitize_detail_value(elem) for elem in elements]
    return item


__all__ = [
    "MESSAGE_MAX_CHARS",
    "TITLE_MAX_CHARS",
    "sanitize_operator_details",
    "sanitize_operator_message",
    "sanitize_title_for_operator",
    "sanitize_url_for_operator_metadata",
]
