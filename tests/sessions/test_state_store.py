"""Tests for sightstalker.sessions.state_store (spec 21.5)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import cast

import pytest

from sightstalker.models import ArtifactRef, BrowserState, ProfileId, RunId, SessionId
from sightstalker.sessions.errors import SessionStateError
from sightstalker.sessions.paths import SessionPaths
from sightstalker.sessions.state_store import BrowserStateStore

_PROFILE = cast(ProfileId, "prof_alpha_default")
_RUN = cast(RunId, "run_auto_0123456789abcdef")
_SESSION = cast(SessionId, "sess_alpha_default")
_DUMMY_SHA = "a" * 64


def _supports_symlinks(tmp_path: Path) -> bool:
    try:
        target = tmp_path / "_probe_t"
        target.mkdir()
        link = tmp_path / "_probe_l"
        link.symlink_to(target)
        link.unlink()
        target.rmdir()
        return True
    except (OSError, NotImplementedError):
        return False


def _state(cookies: tuple[dict[str, object], ...] = ()) -> BrowserState:
    return BrowserState(engine_name="mock", cookies=cookies)


def _store(tmp_path: Path) -> tuple[BrowserStateStore, SessionPaths]:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    paths.ensure_run_layout(_PROFILE, _RUN)
    return BrowserStateStore(paths), paths


def _write_raw(paths: SessionPaths, name: str, payload: bytes) -> ArtifactRef:
    """Write raw bytes into the run dir and build a matching ArtifactRef."""
    target = paths.run_dir(_PROFILE, _RUN) / name
    target.write_bytes(payload)
    rel = paths.relative_to_data_dir(target)
    return ArtifactRef(
        artifact_id="art_raw_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=rel,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        mime_type="application/json",
    )


def test_write_initial_writes_json_file(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert (tmp_path.resolve() / ref.relative_path).is_file()


def test_write_final_writes_json_file(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert (tmp_path.resolve() / ref.relative_path).is_file()


def test_relative_path_is_relative(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert not ref.relative_path.is_absolute()


def test_sha256_matches_content(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    raw = (tmp_path.resolve() / ref.relative_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ref.sha256


def test_size_matches_file(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert (tmp_path.resolve() / ref.relative_path).stat().st_size == ref.size_bytes


def test_mime_type_is_json(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert ref.mime_type == "application/json"


def test_initial_artifact_type(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert ref.artifact_type == "storage_state_initial"


def test_final_artifact_type(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert ref.artifact_type == "storage_state_final"


def test_read_round_trips_cookies_and_origins(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    cookies = ({"name": "a", "value": "1"},)
    ref = store.write_initial_state(
        profile_id=_PROFILE,
        run_id=_RUN,
        session_id=_SESSION,
        state=BrowserState(engine_name="mock", cookies=cookies),
    )
    loaded = store.read_state(ref)
    assert loaded.cookies == cookies
    assert loaded.engine_name == "mock"


def test_read_verifies_hash(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    tampered = ref.model_copy(update={"sha256": "b" * 64})
    with pytest.raises(SessionStateError):
        store.read_state(tampered)


def test_read_verifies_size(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    tampered = ref.model_copy(update={"size_bytes": ref.size_bytes + 1})
    with pytest.raises(SessionStateError):
        store.read_state(tampered)


def test_read_rejects_non_storage_type(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    bad = ref.model_copy(update={"artifact_type": "screenshot"})
    with pytest.raises(SessionStateError):
        store.read_state(bad)


def test_read_rejects_absolute_path(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = ArtifactRef(
        artifact_id="art_raw_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=Path("/etc/passwd"),
        sha256=_DUMMY_SHA,
        size_bytes=1,
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_read_rejects_path_traversal(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    ref = ArtifactRef(
        artifact_id="art_raw_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=Path("..") / ".." / "outside.json",
        sha256=_DUMMY_SHA,
        size_bytes=1,
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_read_rejects_symlinked_state_file(tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("platform does not support symlinks")
    store, paths = _store(tmp_path)
    outside = tmp_path.parent / "evil.json"
    outside.write_bytes(b"{}")
    link = paths.run_dir(_PROFILE, _RUN) / "linked.json"
    link.symlink_to(outside)
    payload = b"{}"
    ref = ArtifactRef(
        artifact_id="art_raw_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=paths.relative_to_data_dir(paths.run_dir(_PROFILE, _RUN))
        / "linked.json",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_read_rejects_symlinked_run_dir(tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("platform does not support symlinks")
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    store = BrowserStateStore(paths)
    # Replace the run dir with a symlink to an outside directory.
    outside = tmp_path.parent / "outside_run"
    outside.mkdir(exist_ok=True)
    (outside / "storage_state.final.json").write_bytes(b"{}")
    run_dir = paths.run_dir(_PROFILE, _RUN)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.symlink_to(outside, target_is_directory=True)
    payload = b"{}"
    ref = ArtifactRef(
        artifact_id="art_raw_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=paths.relative_to_data_dir(run_dir.parent)
        / _RUN
        / "storage_state.final.json",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_existing_final_not_overwritten(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.write_final_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    with pytest.raises(SessionStateError):
        store.write_final_state(
            profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
        )


def test_existing_initial_not_overwritten(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    with pytest.raises(SessionStateError):
        store.write_initial_state(
            profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
        )


def test_pre_existing_target_errors_not_replaced(tmp_path: Path) -> None:
    store, paths = _store(tmp_path)
    target = paths.storage_state_final_path(_PROFILE, _RUN)
    target.write_bytes(b'{"sentinel": true}')
    with pytest.raises(SessionStateError):
        store.write_final_state(
            profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
        )
    # The pre-existing content must be intact (no replacement occurred).
    assert target.read_bytes() == b'{"sentinel": true}'


def test_no_temp_file_left_after_write(tmp_path: Path) -> None:
    store, paths = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    leftovers = [
        p.name
        for p in paths.run_dir(_PROFILE, _RUN).iterdir()
        if p.suffix in (".tmp", ".partial") or p.name.startswith(".tmp")
    ]
    assert leftovers == []


def test_file_permissions_best_effort(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions not enforced on this platform")
    store, _ = _store(tmp_path)
    ref = store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    mode = (tmp_path.resolve() / ref.relative_path).stat().st_mode & 0o777
    assert mode == 0o600


def test_directory_permissions_best_effort(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions not enforced on this platform")
    store, paths = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    mode = paths.run_dir(_PROFILE, _RUN).stat().st_mode & 0o777
    assert mode == 0o700


def test_store_does_not_create_cookies_json(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert list(tmp_path.rglob("cookies.json")) == []


def test_store_does_not_create_latest_json(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.write_initial_state(
        profile_id=_PROFILE, run_id=_RUN, session_id=_SESSION, state=_state()
    )
    assert list(tmp_path.rglob("latest.json")) == []


def test_cast_profile_traversal_no_file_outside(tmp_path: Path) -> None:
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


def test_cast_run_traversal_no_file_outside(tmp_path: Path) -> None:
    paths = SessionPaths(tmp_path)
    paths.ensure_profile_layout(_PROFILE)
    store = BrowserStateStore(paths)
    before = sorted(p.name for p in tmp_path.parent.iterdir())
    with pytest.raises(Exception):
        store.write_initial_state(
            profile_id=_PROFILE,
            run_id=cast(RunId, "../bad"),
            session_id=_SESSION,
            state=_state(),
        )
    after = sorted(p.name for p in tmp_path.parent.iterdir())
    assert before == after


def test_corrupt_json_read_raises(tmp_path: Path) -> None:
    store, paths = _store(tmp_path)
    ref = _write_raw(paths, "corrupt.json", b"{not valid json")
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_pydantic_invalid_read_raises(tmp_path: Path) -> None:
    store, paths = _store(tmp_path)
    # Valid JSON, invalid BrowserState (missing engine_name, extra forbidden).
    ref = _write_raw(paths, "invalid.json", b'{"not_a_field": 1}')
    with pytest.raises(SessionStateError):
        store.read_state(ref)


def test_missing_file_read_raises(tmp_path: Path) -> None:
    store, paths = _store(tmp_path)
    rel = paths.relative_to_data_dir(
        paths.run_dir(_PROFILE, _RUN) / "does_not_exist.json"
    )
    ref = ArtifactRef(
        artifact_id="art_raw_0123456789abcdef",
        artifact_type="storage_state_final",
        relative_path=rel,
        sha256=_DUMMY_SHA,
        size_bytes=2,
        mime_type="application/json",
    )
    with pytest.raises(SessionStateError):
        store.read_state(ref)
