"""Architecture-doc doctrine tests for BEHAVIOR-SPEC-1.

Verifies ``docs/architecture/behavior-boundary.md`` exists and contains the
required doctrine: opt-in + default-disabled behavior, explicit-seed
determinism, environment-vs-interaction separation, ops-as-composition-root,
engines-adapter-only, resolver merge precedence, immutable effective config,
the ContextInitializer seam, the PageInteractionTarget bounds, the persistence
boundary, and the current-vs-future status matrix.

These are content checks over canonical doctrine sentences, not brittle
whole-line matches.
"""

from __future__ import annotations

from pathlib import Path

import sightstalker

_REPO_ROOT = Path(sightstalker.__file__).resolve().parents[2]
_DOC = _REPO_ROOT / "docs" / "architecture" / "behavior-boundary.md"


def _doc_text() -> str:
    assert _DOC.is_file(), f"missing architecture doc: {_DOC}"
    return _DOC.read_text(encoding="utf-8")


def _normalized() -> str:
    # Collapse whitespace and drop leading blockquote markers so multi-word
    # doctrine phrases match regardless of source line wrapping.
    lines = [line.lstrip("> ").rstrip() for line in _doc_text().splitlines()]
    return " ".join(" ".join(lines).split())


def test_doc_exists_and_nonempty() -> None:
    assert len(_doc_text().strip()) > 0


def test_required_doctrine_sentences_present() -> None:
    text = _normalized()
    required = [
        "Behavior is opt-in.",
        "Behavior is disabled by default.",
        "Presence of an InteractionProfile alone does not activate behavior.",
        "Deterministic behavior requires an explicit seed.",
        "Missing seed in deterministic mode is a validation error.",
        "Interaction profiles are not environment profiles.",
        "Environment profiles are resolved before engine launch by a future",
        "run override > selected environment profile > session default > "
        "package default",
        "Resolver output is an immutable effective BrowserLaunchConfig",
        "Engines receive already-resolved BrowserLaunchConfig",
        "ContextInitializer runs after BrowserRuntime.new_context() returns",
        "before BrowserContextHandle.new_page() is used",
        "ops is the composition root, not the implementation home",
        "Persistence may store metadata/provenance only",
        "No interaction or environment package is implemented in",
    ]
    missing = [phrase for phrase in required if phrase not in text]
    assert missing == [], f"doc missing required doctrine: {missing}"


def test_page_interaction_target_bounds_present() -> None:
    text = _normalized()
    for bound in (
        "navigation",
        "storage-state access",
        "network interception",
        "credential handling",
        "engine-specific native objects",
    ):
        assert bound in text, f"PageInteractionTarget bound missing: {bound}"


def test_status_matrix_present() -> None:
    text = _normalized()
    # Matrix headers and the future-PR ownership cells.
    for token in (
        "First Allowed PR",
        "ContextConfigResolver",
        "ContextInitializer",
        "EnvironmentProfile",
        "InteractionProfile",
        "InteractionSimulator",
        "PageInteractionTarget",
        "ENVIRONMENT-1",
        "CONTEXT-INITIALIZER-1",
        "INTERACTION-1",
        "CLI-OPT-IN-1",
    ):
        assert token in text, f"status matrix missing: {token}"


def test_guard_class_labels_documented() -> None:
    text = _normalized()
    assert "PERMANENT" in text
    assert "SNAPSHOT-v0.4.3" in text


def test_doc_cites_readme_as_broader_source() -> None:
    text = _normalized()
    assert "README" in text
    # Specialization relationship, not contradiction.
    assert "specializes" in text or "specialization" in text


def test_doc_states_packaging_and_no_implementation() -> None:
    text = _normalized()
    # The doc must clearly disclaim implemented runtime capability.
    assert "implemented runtime capability" in text
    assert "No interaction or environment package is implemented in" in text
