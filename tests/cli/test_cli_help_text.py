"""Help text must not contain target-specific or bypass/stealth language."""

from __future__ import annotations

from typer.testing import CliRunner

from sightstalker.cli.main import app

runner = CliRunner()

_FORBIDDEN_TERMS = [
    "captcha",
    "stealth",
    "scrape",
    "scraping",
    "anti-fraud",
    "anti-bot",
    "credential stuffing",
    "bypass",
    "evasion",
]

_FORBIDDEN_DOMAINS = [
    "google.com",
    "facebook.com",
    "amazon.com",
    "linkedin.com",
]

_HELP_TARGETS = [
    ["--help"],
    ["config", "--help"],
    ["db", "--help"],
    ["profile", "--help"],
    ["session", "--help"],
    ["run", "--help"],
    ["diag", "--help"],
    ["run", "open", "--help"],
    ["diag", "screenshot", "--help"],
    ["diag", "trace", "--help"],
    ["diag", "console", "--help"],
    ["profile", "create", "--help"],
    ["session", "create", "--help"],
]


def _all_help_text() -> str:
    chunks: list[str] = []
    for args in _HELP_TARGETS:
        result = runner.invoke(app, args)
        assert result.exit_code == 0, args
        chunks.append(result.stdout.lower())
    return "\n".join(chunks)


def test_help_has_no_forbidden_terms() -> None:
    text = _all_help_text()
    for term in _FORBIDDEN_TERMS:
        assert term not in text, term


def test_help_has_no_target_domains() -> None:
    text = _all_help_text()
    for domain in _FORBIDDEN_DOMAINS:
        assert domain not in text, domain
