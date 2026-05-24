"""Artifact repository tests (spec 19.9)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sightstalker.models import ArtifactRef
from sightstalker.persistence import (
    ArtifactRepository,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
    ProfileRepository,
    RunRepository,
    SessionRepository,
)

from tests.persistence._factories import (
    RUN_ID,
    SESSION_ID,
    artifact_ref,
    profile_record,
    run_record,
    session_record,
)


async def _seed_run(session: AsyncSession, tmp_path: Path) -> None:
    await ProfileRepository(session, data_dir=tmp_path / "data").create(
        profile_record(tmp_path / "data")
    )
    await SessionRepository(session).create(session_record())
    await RunRepository(session).create(run_record())


async def test_create_artifact(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        created = await ArtifactRepository(session).create(artifact_ref())
    assert created.artifact_id == "art_init_0123456789abcdef"


async def test_get_artifact(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await ArtifactRepository(session).create(artifact_ref())
    got = await ArtifactRepository(session).get("art_init_0123456789abcdef")
    assert got is not None


async def test_require_missing_raises(session: AsyncSession, tmp_path: Path) -> None:
    with pytest.raises(PersistenceNotFoundError):
        await ArtifactRepository(session).require("art_missing_0123456789ab")


async def test_duplicate_artifact_raises(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await ArtifactRepository(session).create(artifact_ref())
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(artifact_ref())


async def test_absolute_path_rejected(session: AsyncSession, tmp_path: Path) -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="screenshot",
        relative_path=Path("/etc/passwd"),
        sha256="a" * 64,
        size_bytes=1,
        mime_type="image/png",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(bad)


async def test_traversal_path_rejected(session: AsyncSession, tmp_path: Path) -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="screenshot",
        relative_path=Path("..") / "x.png",
        sha256="a" * 64,
        size_bytes=1,
        mime_type="image/png",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(bad)


async def test_bad_hash_rejected(session: AsyncSession, tmp_path: Path) -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="screenshot",
        relative_path=Path("r/x.png"),
        sha256="ZZZ",
        size_bytes=1,
        mime_type="image/png",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(bad)


async def test_negative_size_rejected(session: AsyncSession, tmp_path: Path) -> None:
    bad = ArtifactRef.model_construct(
        artifact_id="art_x_0123456789abcdef",
        artifact_type="screenshot",
        relative_path=Path("r/x.png"),
        sha256="a" * 64,
        size_bytes=-1,
        mime_type="image/png",
        hash_algorithm="sha256",
    )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(bad)


async def test_run_id_without_run_order_rejected(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_run(session, tmp_path)
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(artifact_ref(), run_id=RUN_ID)


async def test_duplicate_run_order_rejected(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_run(session, tmp_path)
        await ArtifactRepository(session).create(
            artifact_ref(artifact_id="art_a_0123456789abcdef", path="r/a.json"),
            run_id=RUN_ID,
            run_order=0,
        )
    with pytest.raises(PersistenceIntegrityError):
        async with session.begin():
            await ArtifactRepository(session).create(
                artifact_ref(artifact_id="art_b_0123456789abcdef", path="r/b.json"),
                run_id=RUN_ID,
                run_order=0,
            )


async def test_list_for_run_ordered_by_run_order(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_run(session, tmp_path)
        repo = ArtifactRepository(session)
        await repo.create(
            artifact_ref(artifact_id="art_b_0123456789abcdef", path="r/b.json"),
            run_id=RUN_ID,
            run_order=1,
        )
        await repo.create(
            artifact_ref(artifact_id="art_a_0123456789abcdef", path="r/a.json"),
            run_id=RUN_ID,
            run_order=0,
        )
    listed = await ArtifactRepository(session).list_for_run(RUN_ID)
    assert [a.artifact_id for a in listed] == [
        "art_a_0123456789abcdef",
        "art_b_0123456789abcdef",
    ]


async def test_list_for_session_ordered(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_run(session, tmp_path)
        await ArtifactRepository(session).create(
            artifact_ref(), session_id=SESSION_ID
        )
    listed = await ArtifactRepository(session).list_for_session(SESSION_ID)
    assert len(listed) == 1


async def test_list_by_type_ordered(session: AsyncSession, tmp_path: Path) -> None:
    async with session.begin():
        await ArtifactRepository(session).create(artifact_ref())
    listed = await ArtifactRepository(session).list_by_type("storage_state_initial")
    assert len(listed) == 1


async def test_list_validates_positive_limit(
    session: AsyncSession, tmp_path: Path
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        await ArtifactRepository(session).list_for_session(SESSION_ID, limit=0)
    with pytest.raises(PersistenceIntegrityError):
        await ArtifactRepository(session).list_by_type("screenshot", limit=-1)


async def test_run_artifact_order_preserved(
    session: AsyncSession, tmp_path: Path
) -> None:
    async with session.begin():
        await _seed_run(session, tmp_path)
        repo = ArtifactRepository(session)
        for i in range(3):
            await repo.create(
                artifact_ref(
                    artifact_id=f"art_n{i}_0123456789abcd", path=f"r/{i}.json"
                ),
                run_id=RUN_ID,
                run_order=i,
            )
    listed = await ArtifactRepository(session).list_for_run(RUN_ID)
    assert [a.artifact_id for a in listed] == [
        "art_n0_0123456789abcd",
        "art_n1_0123456789abcd",
        "art_n2_0123456789abcd",
    ]


def test_artifact_repo_does_not_import_artifact_manager() -> None:
    import sightstalker.persistence.repositories as repo_mod

    src = Path(repo_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "artifacts.manager" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "artifacts.manager" not in alias.name
