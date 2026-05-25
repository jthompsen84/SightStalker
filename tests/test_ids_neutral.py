"""Neutral ID module tests (spec 8.2, 19).

Confirms that sightstalker.ids generates valid identifiers and that
sightstalker.sessions.ids delegates to it, preserving existing public behavior
(including the session-layer "state" fallback prefix).
"""

from __future__ import annotations

import re

from sightstalker import ids as neutral_ids
from sightstalker.sessions import ids as session_ids

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")


def test_neutral_new_run_id_valid() -> None:
    rid = neutral_ids.new_run_id()
    assert rid.startswith("run_")
    assert _ID_RE.match(rid)


def test_neutral_new_context_id_valid() -> None:
    cid = neutral_ids.new_context_id()
    assert cid.startswith("ctx_")
    assert _ID_RE.match(cid)


def test_neutral_new_artifact_id_valid() -> None:
    aid = neutral_ids.new_artifact_id()
    assert aid.startswith("art_")
    assert _ID_RE.match(aid)


def test_neutral_default_prefix_is_artifact() -> None:
    aid = neutral_ids.new_artifact_id()
    assert aid.startswith("art_artifact_")


def test_neutral_empty_prefix_falls_back_to_artifact() -> None:
    aid = neutral_ids.new_artifact_id("")
    assert aid.startswith("art_artifact_")
    assert _ID_RE.match(aid)


def test_session_default_prefix_is_state() -> None:
    # Session layer preserves its historical "state" fallback.
    aid = session_ids.new_artifact_id("")
    assert aid.startswith("art_state_")
    assert _ID_RE.match(aid)


def test_session_delegates_run_and_context() -> None:
    rid = session_ids.new_run_id()
    cid = session_ids.new_context_id()
    assert rid.startswith("run_")
    assert cid.startswith("ctx_")
    assert _ID_RE.match(rid)
    assert _ID_RE.match(cid)


def test_prefix_sanitization_shared() -> None:
    # Both layers sanitize disallowed characters identically.
    n = neutral_ids.new_artifact_id("My Weird/Prefix!!")
    s = session_ids.new_artifact_id("My Weird/Prefix!!")
    for aid in (n, s):
        assert " " not in aid
        assert "/" not in aid
        assert "!" not in aid
        assert _ID_RE.match(aid)


def test_overlong_prefix_truncated_both() -> None:
    for aid in (
        neutral_ids.new_artifact_id("x" * 100),
        session_ids.new_artifact_id("x" * 100),
    ):
        assert len(aid) <= 64
        assert _ID_RE.match(aid)


def test_generated_ids_unique() -> None:
    runs = {neutral_ids.new_run_id() for _ in range(50)}
    artifacts = {neutral_ids.new_artifact_id() for _ in range(50)}
    assert len(runs) == 50
    assert len(artifacts) == 50


def test_safe_artifact_prefix_public_helper() -> None:
    assert neutral_ids.safe_artifact_prefix("") == "artifact"
    assert neutral_ids.safe_artifact_prefix("", fallback="state") == "state"
    assert neutral_ids.safe_artifact_prefix("a/b c") == "a_b_c"


def test_new_profile_id_valid() -> None:
    pid = neutral_ids.new_profile_id()
    assert pid.startswith("prof_")
    assert _ID_RE.match(pid[len("prof_") - 1 :]) or _ID_RE.match(pid)


def test_new_session_id_valid() -> None:
    sid = neutral_ids.new_session_id()
    assert sid.startswith("sess_")
    assert _ID_RE.match(sid)


def test_new_profile_and_session_ids_match_model_patterns() -> None:
    from pydantic import TypeAdapter

    from sightstalker.models import ProfileId, SessionId

    TypeAdapter(ProfileId).validate_python(neutral_ids.new_profile_id())
    TypeAdapter(SessionId).validate_python(neutral_ids.new_session_id())


def test_new_profile_and_session_ids_unique() -> None:
    profiles = {neutral_ids.new_profile_id() for _ in range(50)}
    sessions = {neutral_ids.new_session_id() for _ in range(50)}
    assert len(profiles) == 50
    assert len(sessions) == 50


# ---------------------------------------------------------------------------
# CLI-RUNNER-1: neutral profile/session ID helpers
# ---------------------------------------------------------------------------


def test_neutral_new_profile_id_valid() -> None:
    pid = neutral_ids.new_profile_id()
    assert pid.startswith("prof_")
    assert _ID_RE.match(pid[len("prof_"):])
    # Conforms to the accepted ProfileId pattern at the model boundary.
    from sightstalker.sessions.ids import validate_profile_id

    assert validate_profile_id(pid) == pid


def test_neutral_new_session_id_valid() -> None:
    sid = neutral_ids.new_session_id()
    assert sid.startswith("sess_")
    assert _ID_RE.match(sid[len("sess_"):])
    from sightstalker.sessions.ids import validate_session_id

    assert validate_session_id(sid) == sid


def test_neutral_profile_and_session_ids_unique() -> None:
    profiles = {neutral_ids.new_profile_id() for _ in range(50)}
    sessions = {neutral_ids.new_session_id() for _ in range(50)}
    assert len(profiles) == 50
    assert len(sessions) == 50
