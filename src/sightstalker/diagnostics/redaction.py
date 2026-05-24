"""
sightstalker.diagnostics.redaction — strict diagnostics-local redaction.

Console output is high-risk free-form text that can contain bearer tokens,
JWTs, cookie strings, and authorization material that the shared key=value
redactor does not catch. This module layers additional strict patterns on top
of ``sightstalker.security.redaction`` for diagnostic console text and console
``location`` mappings.

This module does not modify the shared redactor; it composes it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sightstalker.models import JsonObject
from sightstalker.security.redaction import redact_mapping, redact_string

_REDACTED = "<redacted>"

# Bearer tokens: "Bearer <token>" / "Authorization: Bearer <token>".
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{4,}")

# JWT-like tokens: three base64url segments separated by dots.
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}"
)

# Cookie / Set-Cookie header forms with an inline value.
_COOKIE_RE = re.compile(
    r"(?i)\b(set-cookie|cookie)\s*:\s*[^\r\n]+"
)

# Authorization header form with an inline value.
_AUTHORIZATION_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization)\s*:\s*[^\r\n]+"
)


def redact_console_text(value: str) -> str:
    """Strictly redact a console text line.

    Applies the shared key=value redactor, then strips bearer tokens, JWTs,
    and cookie/authorization header forms.
    """
    redacted = redact_string(value)
    redacted = _AUTHORIZATION_RE.sub(lambda m: f"{m.group(1)}: {_REDACTED}", redacted)
    redacted = _COOKIE_RE.sub(lambda m: f"{m.group(1)}: {_REDACTED}", redacted)
    redacted = _BEARER_RE.sub(f"Bearer {_REDACTED}", redacted)
    redacted = _JWT_RE.sub(_REDACTED, redacted)
    return redacted


def redact_console_location(location: Mapping[str, Any] | None) -> JsonObject | None:
    """Redact a console ``location`` mapping, scrubbing nested string values."""
    if location is None:
        return None
    redacted = redact_mapping(location)
    # Strip strict console patterns from any surviving string values (e.g. a
    # URL field carrying a token query parameter).
    result: JsonObject = {}
    for key, value in redacted.items():
        if isinstance(value, str):
            result[key] = redact_console_text(value)
        else:
            result[key] = value
    return result
