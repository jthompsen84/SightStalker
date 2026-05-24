"""Tests for sightstalker.sessions.ids (spec 21.2)."""

from __future__ import annotations

import re
from typing import cast

import pytest

from sightstalker.models import ArtifactId, ContextId, ProfileId, RunId
from sightstalker.sessions.ids import (
    new_artifact_id,
    new_context_id,
    new_run_id,
    validate_artifact_id,
    validate_context_id,
    validate_profile_id,
    validate_run_id,
)

# Accepted identifier regex contract (mirrors the models' StringConstraints).
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")


def test_new_run_id_validates_as_run_id() -> None:
    run_id = new_run_id()
    assert validate_run_id(run_id) == run_id
    assert run_id.startswith("run_")
    assert _ID_RE.match(run_id)


def test_new_context_id_validates_as_context_id() -> None:
    context_id = new_context_id()
    assert validate_context_id(context_id) == context_id
    assert context_id.startswith("ctx_")
    assert _ID_RE.match(context_id)


def test_new_artifact_id_validates_as_artifact_id() -> None:
    artifact_id = new_artifact_id()
    assert validate_artifact_id(artifact_id) == artifact_id
    assert artifact_id.startswith("art_")
    assert _ID_RE.match(artifact_id)


def test_artifact_prefix_is_sanitized() -> None:
    artifact_id = new_artifact_id("My Weird/Prefix!!")
    # Disallowed characters must not survive into the identifier body.
    assert " " not in artifact_id
    assert "/" not in artifact_id
    assert "!" not in artifact_id
    assert _ID_RE.match(artifact_id)


def test_new_artifact_id_empty_prefix_validates() -> None:
    artifact_id = new_artifact_id("")
    assert validate_artifact_id(artifact_id) == artifact_id
    assert _ID_RE.match(artifact_id)


def test_new_artifact_id_punctuation_only_prefix_validates() -> None:
    artifact_id = new_artifact_id("-!")
    assert validate_artifact_id(artifact_id) == artifact_id
    assert _ID_RE.match(artifact_id)


def test_new_artifact_id_overlong_prefix_validates() -> None:
    artifact_id = new_artifact_id("x" * 100)
    assert validate_artifact_id(artifact_id) == artifact_id
    assert _ID_RE.match(artifact_id)


def test_generated_ids_are_unique_across_calls() -> None:
    runs = {new_run_id() for _ in range(50)}
    contexts = {new_context_id() for _ in range(50)}
    artifacts = {new_artifact_id() for _ in range(50)}
    assert len(runs) == 50
    assert len(contexts) == 50
    assert len(artifacts) == 50


def test_generated_ids_under_regex_max_length() -> None:
    for _ in range(25):
        assert len(new_run_id()) <= 64
        assert len(new_context_id()) <= 64
        assert len(new_artifact_id("x" * 100)) <= 64


def test_validators_reject_malformed_cast_strings() -> None:
    with pytest.raises(Exception):
        validate_profile_id(cast(ProfileId, "../../outside"))
    with pytest.raises(Exception):
        validate_run_id(cast(RunId, "../bad"))
    with pytest.raises(Exception):
        validate_context_id(cast(ContextId, "no"))
    with pytest.raises(Exception):
        validate_artifact_id(cast(ArtifactId, "bad/slash"))
