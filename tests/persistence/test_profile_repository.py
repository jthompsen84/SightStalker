"""Profile repository tests (spec 19.6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sightstalker.persistence import (
    PersistenceIntegrityError,
    PersistenceNotFoundError,
    ProfileRepository,
)
from sightstalker.models import ProfileRecord

from tests.persistence._factories import PROFILE_ID, profile_record


def _repo(session: AsyncSession, tmp_path: Path) -> ProfileRepository:
    return ProfileRepository(session, data_dir=tmp_path / "data")


async def test_create_profile(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        created = await repo.create(profile_record(tmp_path / "data"))
    assert created.profile_id == PROFILE_ID
    assert created.active_lock_path is None


async def test_get_profile(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(profile_record(tmp_path / "data"))
    got = await repo.get(PROFILE_ID)
    assert got is not None and got.profile_id == PROFILE_ID


async def test_require_profile(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(profile_record(tmp_path / "data"))
    got = await repo.require(PROFILE_ID)
    assert got.profile_id == PROFILE_ID


async def test_require_missing_raises(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    with pytest.raises(PersistenceNotFoundError):
        await repo.require("prof_missing_00000000")


async def test_list_profiles(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(profile_record(tmp_path / "data"))
        await repo.create(
            profile_record(tmp_path / "data", profile_id="prof_beta_default0")
        )
    listed = await repo.list()
    assert len(listed) == 2


async def test_list_validates_positive_limit(
    session: AsyncSession, tmp_path: Path
) -> None:
    repo = _repo(session, tmp_path)
    with pytest.raises(PersistenceIntegrityError):
        await repo.list(limit=0)
    with pytest.raises(PersistenceIntegrityError):
        await repo.list(limit=-1)


async def test_archive_profile(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(profile_record(tmp_path / "data"))
        archived = await repo.archive(PROFILE_ID)
    assert archived.archived is True
    assert archived.updated_at is not None


async def test_archived_excluded_by_default(
    session: AsyncSession, tmp_path: Path
) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(profile_record(tmp_path / "data"))
        await repo.archive(PROFILE_ID)
    assert await repo.list() == []
    assert len(await repo.list(include_archived=True)) == 1


async def test_duplicate_create_raises(
    session: AsyncSession, tmp_path: Path
) -> None:
    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(profile_record(tmp_path / "data"))
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await repo.create(profile_record(tmp_path / "data"))


async def test_empty_name_rejected(session: AsyncSession, tmp_path: Path) -> None:
    repo = _repo(session, tmp_path)
    bad = ProfileRecord(
        profile_id=PROFILE_ID,
        name="   ",
        profile_dir=tmp_path / "data" / "profiles" / PROFILE_ID,
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await repo.create(bad)


async def test_absolute_contained_profile_dir_normalized(
    session: AsyncSession, tmp_path: Path
) -> None:
    repo = _repo(session, tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    async with session.begin():
        created = await repo.create(profile_record(tmp_path / "data"))
    # Rehydrated path is absolute and contained under data_dir.
    assert created.profile_dir == (tmp_path / "data" / "profiles" / PROFILE_ID)


async def test_absolute_outside_profile_dir_rejected(
    session: AsyncSession, tmp_path: Path
) -> None:
    from sightstalker.persistence import PersistenceSecurityError

    repo = _repo(session, tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    bad = ProfileRecord(
        profile_id=PROFILE_ID,
        name="alpha",
        profile_dir=tmp_path / "elsewhere",
    )
    with pytest.raises(PersistenceSecurityError):
        async with session.begin():
            await repo.create(bad)


async def test_active_lock_path_not_persisted(
    session: AsyncSession, tmp_path: Path
) -> None:
    from sqlalchemy import text

    repo = _repo(session, tmp_path)
    async with session.begin():
        await repo.create(
            ProfileRecord(
                profile_id=PROFILE_ID,
                name="alpha",
                profile_dir=tmp_path / "data" / "profiles" / PROFILE_ID,
                active_lock_path=Path("/tmp/secret.lock"),
            )
        )
    rows = (await session.execute(text("SELECT * FROM profiles"))).mappings().all()
    for row in rows:
        assert "active_lock_path" not in row.keys()
        assert "/tmp/secret.lock" not in str(dict(row))
