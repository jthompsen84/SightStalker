"""Session-state delegation integration tests (spec 14, 19, 23).

Confirms that delegating BrowserStateStore onto ArtifactManager preserves the
SESSION-STATE-1 contract: file names, ref shape, no-overwrite, path containment,
no trailing newline, no cookies.json/latest.json, and SessionStateError wrapping
of all artifact-layer failures.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from sightstalker.artifacts import ArtifactManager, ArtifactPaths
from sightstalker.models import ArtifactRef, BrowserState, ProfileId, RunId, SessionId
from sightstalker.sessions.errors import SessionStateError
from sightstalker.sessions.paths import SessionPaths
from sightstalker.sessions.state_store import BrowserStateStore

_PROFILE = cast(ProfileId, "prof_alpha_default")
_RUN = cast(RunId, "run_auto_0123456789abcdef")
_SESSION = cast(SessionId, "sess_alpha_default")


def _store(tmp_path: Path) -> tuple[BrowserStateStore, SessionPaths]:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    return BrowserStateStore(paths), paths


def _state() -> BrowserState:
    return BrowserState(engine_name="mock", cookies=({"name": "c", "value": "v"},))


def test_default_constructor_still_works(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    store = BrowserStateStore(paths)  # no injected manager
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert ref.artifact_type == "storage_state_initial"


def test_injected_manager_accepted(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    manager = ArtifactManager(ArtifactPaths(paths.data_dir))
    store = BrowserStateStore(paths, artifact_manager=manager)
    ref = store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert ref.artifact_type == "storage_state_final"


def test_filenames_preserved(tmp_path: Path) -> None:
    store, paths = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    run_dir = paths.run_dir(_PROFILE, _RUN)
    assert (run_dir / "storage_state.initial.json").is_file()
    assert (run_dir / "storage_state.final.json").is_file()


def test_no_trailing_newline_preserved(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    raw = (tmp_path.resolve() / ref.relative_path).read_bytes()
    assert not raw.endswith(b"\n")


def test_ref_shape_preserved(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert not ref.relative_path.is_absolute()
    assert ref.mime_type == "application/json"
    assert ref.hash_algorithm == "sha256"
    assert len(ref.sha256) == 64
    assert ref.artifact_id.startswith("art_init_")


def test_round_trip_via_read_state(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    cookies = ({"name": "sess", "value": "abc"},)
    ref = store.write_initial_state(
        profile_id=_PROFILE,
        run_id=_RUN,
        session_id=_SESSION,
        state=BrowserState(engine_name="mock", cookies=cookies),
    )
    loaded = store.read_state(ref)
    assert loaded.cookies == cookies


def test_no_overwrite_preserved(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    with pytest.raises(SessionStateError):
        store.write_final_state(
            profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
        )


def test_tampered_state_raises_session_error(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    bad = ref.model_copy(update={"sha256": "b" * 64})
    with pytest.raises(SessionStateError):
        store.read_state(bad)


def test_missing_state_raises_session_error(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    (tmp_path.resolve() / ref.relative_path).unlink()
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_non_storage_type_raises_session_error(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    bad = ref.model_copy(update={"artifact_type": "screenshot"})
    with pytest.raises(SessionStateError):
        store.read_state(bad)


def test_absolute_path_ref_raises_session_error(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = ArtifactRef(
        artifact_id="art_init_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=Path("/etc/passwd"),
        sha256="a" * 64,
        size_bytes=1,
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_non_object_json_raises_session_error(tmp_path: Path) -> None:
    from sightstalker.artifacts.hashing import compute_sha256

    store, paths = _store(tmp_path)
    # Write a JSON array (valid JSON, not an object) at a state path.
    target = paths.storage_state_final_path(_PROFILE, _RUN)
    payload = b"[1,2,3]"
    target.write_bytes(payload)
    ref = ArtifactRef(
        artifact_id="art_final_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=paths.relative_to_data_dir(target),
        sha256=compute_sha256(payload),
        size_bytes=len(payload),
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_no_cookies_json_no_latest_json(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert list(tmp_path.rglob("cookies.json")) == []
    assert list(tmp_path.rglob("latest.json")) == []


def test_cast_traversal_creates_nothing_outside(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    store = BrowserStateStore(paths)
    before = sorted(p.name for p in tmp_path.parent.iterdir())
    with pytest.raises(Exception):
        store.write_initial_state(
            profile_id=cast(ProfileId, "../../outside"),
            run_id=_RUN,
            session_id=_SESSION,
            state=_state(),
        )
    after = sorted(p.name for p in tmp_path.parent.iterdir())
    assert before == after
