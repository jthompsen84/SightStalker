"""README claim guard for BEHAVIOR-SPEC-1.

Scans the whole README and asserts it does not claim future
interaction/environment capability as currently implemented. The check is
baseline-aware: it allows future/planned/not-yet/negated/disclaimer contexts and
only flags positive current-capability claim phrases. It does not ban bare
tokens like "interaction" or "fingerprint" (which legitimately appear in
disclaimers and future sections).
"""

from __future__ import annotations

import re
from pathlib import Path

import sightstalker

_REPO_ROOT = Path(sightstalker.__file__).resolve().parents[2]
_README = _REPO_ROOT / "README.md"

# Phrases that, in a positive/current context, would over-claim future work.
# Matched case-insensitively as whole phrases.
_POSITIVE_CLAIM_PATTERNS = [
    r"supports interaction profiles",
    r"supports environment profiles",
    r"includes an interaction simulator",
    r"applies fingerprint profiles",
    r"simulates (typing|clicking|scrolling)",
    r"deterministic interaction simulation",
]

# Markers that make a line a future/planned/negated/disclaimer context.
_ALLOW_CONTEXT = re.compile(
    r"(future|planned|roadmap|not yet|not implemented|deferred|does not|"
    r"doesn't|do not|no\b|never|without|is not|are not|cannot|"
    r"remain[s]? deferred|guardrail|spec PR|v0\.4\.\d)",
    re.IGNORECASE,
)

# Section headings that establish a future/negated context for following lines.
_FUTURE_HEADING = re.compile(
    r"(future|planned|roadmap|not yet|deferred|does not yet include|"
    r"authorized-use|non-goal)",
    re.IGNORECASE,
)


def _readme_text() -> str:
    assert _README.is_file(), f"missing README: {_README}"
    return _README.read_text(encoding="utf-8")


def _segments_with_context() -> list[tuple[int, str, bool]]:
    """Return (lineno, segment, in_future_context) for each README sentence.

    Lines are grouped into paragraphs (blank-line separated). Within a
    paragraph, a future/negated marker anywhere in the paragraph — or in the
    governing heading — establishes future context for the whole paragraph, so
    a claim phrase that wraps onto a marker-less line is still recognized as
    future when its sentence/paragraph is future-marked.
    """
    out: list[tuple[int, str, bool]] = []
    heading_is_future = False
    paragraph: list[tuple[int, str]] = []

    def flush() -> None:
        if not paragraph:
            return
        joined = " ".join(text for _, text in paragraph)
        para_is_future = heading_is_future or bool(_ALLOW_CONTEXT.search(joined))
        for lineno, text in paragraph:
            line_is_future = para_is_future or bool(_ALLOW_CONTEXT.search(text))
            out.append((lineno, text, line_is_future))
        paragraph.clear()

    for i, raw in enumerate(_readme_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            flush()
            heading_is_future = bool(_FUTURE_HEADING.search(line))
            out.append((i, line, heading_is_future or bool(_ALLOW_CONTEXT.search(line))))
            continue
        paragraph.append((i, line))
    flush()
    return out


def test_readme_exists() -> None:
    assert len(_readme_text().strip()) > 0


def test_no_positive_future_capability_claims() -> None:
    violations: list[str] = []
    patterns = [re.compile(p, re.IGNORECASE) for p in _POSITIVE_CLAIM_PATTERNS]
    for lineno, line, in_future in _segments_with_context():
        if in_future:
            continue
        for pat in patterns:
            if pat.search(line):
                violations.append(f"L{lineno}: {line!r} matches /{pat.pattern}/")
    assert violations == [], (
        "README makes positive current-capability claims outside "
        f"future/negated context: {violations}"
    )


def test_deterministic_interaction_simulation_not_in_current_feature_list() -> None:
    # The specific known contradiction: the architecture/feature bullet list
    # must not present "Deterministic interaction simulation" as current.
    for lineno, line, in_future in _segments_with_context():
        if line.lower().lstrip("- ").startswith("deterministic interaction"):
            assert in_future, (
                f"L{lineno}: deterministic interaction simulation claimed as "
                "current implemented feature"
            )


def test_no_positive_safety_capability_claims() -> None:
    # Positive evasion/stealth/CAPTCHA/anti-fraud capability claims are banned;
    # negated disclaimers are allowed.
    banned = [
        r"anti-detection",
        r"evasion",
        r"stealth mode",
        r"CAPTCHA (solving|bypass)",
        r"anti-fraud bypass",
        r"credential stuffing",
        r"proxy rotation",
        r"fingerprint generation",
    ]
    patterns = [re.compile(p, re.IGNORECASE) for p in banned]
    violations: list[str] = []
    for lineno, line, in_future in _segments_with_context():
        if in_future:
            continue
        for pat in patterns:
            if pat.search(line):
                violations.append(f"L{lineno}: {line!r} matches /{pat.pattern}/")
    assert violations == [], f"README makes positive safety claims: {violations}"


def test_readme_mentions_v043_spec_status() -> None:
    text = _readme_text().lower()
    assert "v0.4.3" in text
    # The spec/guardrail framing must be present.
    assert "guardrail" in text or "spec pr" in text or "specification" in text


def test_selftest_detects_synthetic_overclaim() -> None:
    # The matcher must flag a positive claim in a non-future context.
    pat = re.compile(r"deterministic interaction simulation", re.IGNORECASE)
    positive_line = "- Deterministic interaction simulation"
    future_line = "Future: deterministic interaction simulation is planned"
    assert pat.search(positive_line)
    assert not _ALLOW_CONTEXT.search(positive_line)
    assert _ALLOW_CONTEXT.search(future_line)
