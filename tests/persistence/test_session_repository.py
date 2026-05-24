"""Session repository tests (spec 19.7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from sightstalker.models import (
    BrowserContextConfig,
    BrowserLaunchConfig,
    ProxyConfig,
    SessionConfig,
    SessionRecord,
)
from sightstalker.persistence import (
    ArtifactRepository,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
    PersistenceSecurityError,
    ProfileRepository,
    SessionRepository,
)

from tests.persistence._factories import (
    PROFILE_ID,
    SESSION_ID,
    artifact_ref,
    profile_record,
    session_record,
)


async def _seed_profile(session: AsyncSession, tmp_path: Path) -> None:
    repo = ProfileRepository(session, data_dir=tmp_path / "data")
    await repo.create(profile_record(tmp_path / "data"))


async def test_create_session_for_existing_profile(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        created = await SessionRepository(session).create(session_record())
    assert created.session_id == SESSION_ID


async def test_create_session_missing_profile_fails(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await SessionRepository(session).create(session_record())


async def test_get_session(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
    got = await SessionRepository(session).get(SESSION_ID)
    assert got is not None and got.session_id == SESSION_ID


async def test_require_missing_raises(session: AsyncSession, tmp_path: Path) -> None:
    with pytest.raises(PersistenceNotFoundError):
        await SessionRepository(session).require("sess_missing_00000000")


async def test_list_sessions_for_profile(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
    listed = await SessionRepository(session).list_for_profile(PROFILE_ID)
    assert len(listed) == 1


async def test_list_validates_positive_limit(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        await SessionRepository(session).list_for_profile(PROFILE_ID, limit=0)


async def test_archive_session(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
        archived = await SessionRepository(session).archive(SESSION_ID)
    assert archived.archived is True
    assert archived.updated_at is not None


async def test_empty_name_rejected(session: AsyncSession, tmp_path: Path) -> None:
    bad = SessionRecord(
        session_id=SESSION_ID,
        name="  ",
        profile_id=PROFILE_ID,
        config=SessionConfig(
            launch=BrowserLaunchConfig(engine_name="mock"),
            context=BrowserContextConfig(),
        ),
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await _seed_profile(session, tmp_path)
            await SessionRepository(session).create(bad)


async def test_safe_config_round_trips(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
    got = await SessionRepository(session).require(SESSION_ID)
    assert got.config.launch.engine_name == "mock"


async def test_unsafe_config_rejected(
    session: AsyncSession, tmp_path: Path
) -> None:
    bad = SessionRecord(
        session_id=SESSION_ID,
        name="s",
        profile_id=PROFILE_ID,
        config=SessionConfig(
            launch=BrowserLaunchConfig(engine_name="mock", env={"SECRET": "x"}),
            context=BrowserContextConfig(),
        ),
    )
    with pytest.raises(PersistenceSecurityError):
        async with session.begin():
            await _seed_profile(session, tmp_path)
            await SessionRepository(session).create(bad)


async def test_proxy_password_masked_dump_still_rejected(
    session: AsyncSession, tmp_path: Path
) -> None:
    bad = SessionRecord(
        session_id=SESSION_ID,
        name="s",
        profile_id=PROFILE_ID,
        config=SessionConfig(
            launch=BrowserLaunchConfig(
                engine_name="mock",
                proxy=ProxyConfig(server="http://p", password=SecretStr("p-123")),
            ),
            context=BrowserContextConfig(),
        ),
    )
    with pytest.raises(PersistenceSecurityError):
        async with session.begin():
            await _seed_profile(session, tmp_path)
            await SessionRepository(session).create(bad)


async def test_set_latest_artifacts(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
        ref = await ArtifactRepository(session).create(
            artifact_ref(), session_id=SESSION_ID
        )
        updated = await SessionRepository(session).set_latest_artifacts(
            session_id=SESSION_ID, latest_initial=ref, latest_final=None
        )
    assert updated.latest_initial_state is not None
    assert updated.latest_initial_state.artifact_id == ref.artifact_id


async def test_latest_refs_rehydrate(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
        ref = await ArtifactRepository(session).create(
            artifact_ref(), session_id=SESSION_ID
        )
        await SessionRepository(session).set_latest_artifacts(
            session_id=SESSION_ID, latest_initial=ref, latest_final=None
        )
    got = await SessionRepository(session).require(SESSION_ID)
    assert got.latest_initial_state is not None
    assert got.latest_initial_state.sha256 == ref.sha256


async def test_missing_artifact_ref_rejected_when_setting_latest(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        await SessionRepository(session).create(session_record())
    # A ref whose artifact row was never inserted violates the FK at flush.
    phantom = artifact_ref(artifact_id="art_phantom_0123456789ab")
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await SessionRepository(session).set_latest_artifacts(
                session_id=SESSION_ID, latest_initial=phantom, latest_final=None
            )


async def test_updated_at_set_on_update(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_profile(session, tmp_path)
        created = await SessionRepository(session).create(session_record())
        updated = await SessionRepository(session).update(created)
    assert updated.updated_at is not None
