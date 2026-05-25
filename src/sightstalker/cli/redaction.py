"""
sightstalker.cli.redaction — CLI URL preparation over resilience sanitizers.

As of v0.4.1 the dependency-light operator sanitizers
(``sanitize_url_for_metadata``, ``sanitize_title_for_output``,
``sanitize_cli_message``) are thin re-exports of the canonical
``sightstalker.resilience.operator_redaction`` helpers, so there is a single
redaction implementation shared by the CLI and resilience logging.

``prepare_navigation_url`` stays here: it is CLI-specific policy (splitting a
raw navigation URL used only in-memory for a single ``page.goto`` from the
redacted metadata URL that is persisted/printed, and refusing unsafe URLs).
Raw navigation URLs and ``data:`` bodies are never persisted or printed.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from sightstalker.cli.errors import CliSecurityError, CliUsageError
from sightstalker.resilience.operator_redaction import (
    MESSAGE_MAX_CHARS,
    TITLE_MAX_CHARS,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_operator_message as sanitize_cli_message,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_title_for_operator as sanitize_title_for_output,
)
from sightstalker.resilience.operator_redaction import (
    sanitize_url_for_operator_metadata as sanitize_url_for_metadata,
)

# Maximum length we accept for a data:text/html URL.
DATA_URL_MAX_CHARS = 4096

_DATA_HTML_PREFIX = "data:text/html"
_REDACTED = "<redacted>"


def _has_control_chars(value: str) -> bool:
    """Return True if ``value`` contains C0/C1 control chars or DEL."""
    for ch in value:
        code = ord(ch)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            return True
    return False


def _prepare_data_url(raw: str) -> tuple[str, str]:
    lowered = raw.lower()
    if not lowered.startswith(_DATA_HTML_PREFIX):
        raise CliSecurityError("only data:text/html URLs are allowed")
    # Next char after the media type must be ';' (params) or ',' (data).
    tail = raw[len(_DATA_HTML_PREFIX) :]
    if tail[:1] not in (",", ";"):
        raise CliSecurityError("only data:text/html URLs are allowed")
    if ";base64" in lowered:
        raise CliSecurityError("base64 data: URLs are not allowed in this release")
    if len(raw) > DATA_URL_MAX_CHARS:
        raise CliSecurityError("data: URL exceeds the allowed size")
    return raw, f"{_DATA_HTML_PREFIX},{_REDACTED}"


def prepare_navigation_url(url: object) -> tuple[str, str]:
    """Validate ``url`` and return ``(raw_navigation_url, metadata_url_redacted)``.

    The raw URL is for a single in-memory ``page.goto`` only; the metadata URL
    is the redacted form persisted in records and printed to operators.

    Raises:
        CliUsageError: for empty / scheme-less / malformed input (exit code 2).
        CliSecurityError: for unsafe input -- embedded credentials, disallowed
            schemes (``file://`` etc.), control characters, oversized or base64
            ``data:`` URLs (exit code 6).
    """
    if not isinstance(url, str):
        raise CliUsageError("URL must be a string")
    raw = url.strip()
    if raw == "":
        raise CliUsageError("URL must not be empty")
    if _has_control_chars(raw):
        raise CliSecurityError("URL must not contain control characters or newlines")

    lowered = raw.lower()
    if lowered == "about:blank":
        return "about:blank", "about:blank"
    if lowered.startswith("data:"):
        return _prepare_data_url(raw)

    parts = urlsplit(raw)
    if parts.scheme == "":
        raise CliUsageError("URL must include a scheme (http or https)")
    if parts.scheme not in ("http", "https"):
        raise CliSecurityError(f"URL scheme '{parts.scheme}' is not allowed")
    if "@" in parts.netloc:
        raise CliSecurityError("URL must not contain embedded credentials")
    if not parts.hostname:
        raise CliUsageError("URL must include a host")

    return raw, sanitize_url_for_metadata(raw)


__all__ = [
    "DATA_URL_MAX_CHARS",
    "MESSAGE_MAX_CHARS",
    "TITLE_MAX_CHARS",
    "prepare_navigation_url",
    "sanitize_cli_message",
    "sanitize_title_for_output",
    "sanitize_url_for_metadata",
]
