"""
sightstalker.persistence.repositories — async metadata repositories.

Six repositories over the metadata schema: profiles, sessions, runs, browser
contexts, artifacts, and health records. All repositories accept a caller-owned
``AsyncSession``; mutating methods ``flush()`` (never ``commit()``) and
translate flush-time ``IntegrityError`` into sanitized
``PersistenceIntegrityError``. Repositories never create engines/sessions,
never store the session beyond a call, and never share a session across tasks.

Linkage ownership: ``ArtifactRepository`` owns run/session artifact linkage and
``run_order``; ``RunRepository`` persists scalar run fields only and rehydrates
``RunRecord.artifacts`` via one ordered query.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sightstalker.models import (
    ArtifactId,
    ArtifactRef,
    ArtifactType,
    BrowserContextRecord,
    ContextId,
    ProfileId,
    ProfileRecord,
    RunId,
    RunRecord,
    SessionHealthRecord,
    SessionId,
    SessionRecord,
    utc_now,
)
from sightstalker.persistence.errors import (
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from sightstalker.persistence.models import (
    ArtifactORM,
    BrowserContextORM,
    HealthRecordORM,
    ProfileORM,
    RunORM,
    SessionORM,
)
from sightstalker.persistence.serialization import (
    artifact_ref_from_row,
    artifact_ref_to_row_values,
    context_from_row,
    context_to_row_values,
    health_from_row,
    health_to_row_values,
    profile_from_row,
    profile_to_row_values,
    run_from_row,
    run_to_row_values,
    session_from_row,
    session_to_row_values,
)


def _check_limit(limit: int | None) -> None:
    if limit is not None and limit <= 0:
        raise PersistenceIntegrityError("limit must be positive when provided")


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise PersistenceIntegrityError(
            "database integrity constraint was violated"
        ) from None


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class ProfileRepository:
    def __init__(self, session: AsyncSession, *, data_dir: Path) -> None:
        self._session = session
        self._data_dir = data_dir

    async def create(self, profile: ProfileRecord) -> ProfileRecord:
        values = profile_to_row_values(profile, data_dir=self._data_dir)
        row = ProfileORM(created_at=profile.created_at or utc_now(), **values)
        self._session.add(row)
        await _flush(self._session)
        return profile_from_row(row, data_dir=self._data_dir)

    async def get(self, profile_id: ProfileId) -> ProfileRecord | None:
        row = await self._session.get(ProfileORM, profile_id)
        if row is None:
            return None
        return profile_from_row(row, data_dir=self._data_dir)

    async def require(self, profile_id: ProfileId) -> ProfileRecord:
        record = await self.get(profile_id)
        if record is None:
            raise PersistenceNotFoundError("profile not found")
        return record

    async def list(
        self, *, include_archived: bool = False, limit: int | None = None
    ) -> list[ProfileRecord]:
        _check_limit(limit)
        stmt = select(ProfileORM)
        if not include_archived:
            stmt = stmt.where(ProfileORM.archived.is_(False))
        stmt = stmt.order_by(
            ProfileORM.created_at.desc(), ProfileORM.profile_id.asc()
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [profile_from_row(r, data_dir=self._data_dir) for r in rows]

    async def archive(self, profile_id: ProfileId) -> ProfileRecord:
        row = await self._session.get(ProfileORM, profile_id)
        if row is None:
            raise PersistenceNotFoundError("profile not found")
        row.archived = True
        row.updated_at = utc_now()
        await _flush(self._session)
        return profile_from_row(row, data_dir=self._data_dir)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _ref_for(self, artifact_id: str | None) -> ArtifactRef | None:
        if artifact_id is None:
            return None
        row = await self._session.get(ArtifactORM, artifact_id)
        if row is None:
            return None
        return artifact_ref_from_row(row)

    async def create(self, session_record: SessionRecord) -> SessionRecord:
        values = session_to_row_values(session_record)
        row = SessionORM(
            created_at=session_record.created_at or utc_now(), **values
        )
        self._session.add(row)
        await _flush(self._session)
        return await self._rehydrate(row)

    async def get(self, session_id: SessionId) -> SessionRecord | None:
        row = await self._session.get(SessionORM, session_id)
        if row is None:
            return None
        return await self._rehydrate(row)

    async def require(self, session_id: SessionId) -> SessionRecord:
        record = await self.get(session_id)
        if record is None:
            raise PersistenceNotFoundError("session not found")
        return record

    async def list_for_profile(
        self,
        profile_id: ProfileId,
        *,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[SessionRecord]:
        _check_limit(limit)
        stmt = select(SessionORM).where(SessionORM.profile_id == profile_id)
        if not include_archived:
            stmt = stmt.where(SessionORM.archived.is_(False))
        stmt = stmt.order_by(
            SessionORM.created_at.desc(), SessionORM.session_id.asc()
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [await self._rehydrate(r) for r in rows]

    async def update(self, session_record: SessionRecord) -> SessionRecord:
        row = await self._session.get(SessionORM, session_record.session_id)
        if row is None:
            raise PersistenceNotFoundError("session not found")
        values = session_to_row_values(session_record)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = utc_now()
        await _flush(self._session)
        return await self._rehydrate(row)

    async def set_latest_artifacts(
        self,
        *,
        session_id: SessionId,
        latest_initial: ArtifactRef | None,
        latest_final: ArtifactRef | None,
    ) -> SessionRecord:
        row = await self._session.get(SessionORM, session_id)
        if row is None:
            raise PersistenceNotFoundError("session not found")
        row.latest_initial_artifact_id = (
            latest_initial.artifact_id if latest_initial is not None else None
        )
        row.latest_final_artifact_id = (
            latest_final.artifact_id if latest_final is not None else None
        )
        row.updated_at = utc_now()
        await _flush(self._session)
        return await self._rehydrate(row)

    async def archive(self, session_id: SessionId) -> SessionRecord:
        row = await self._session.get(SessionORM, session_id)
        if row is None:
            raise PersistenceNotFoundError("session not found")
        row.archived = True
        row.updated_at = utc_now()
        await _flush(self._session)
        return await self._rehydrate(row)

    async def _rehydrate(self, row: SessionORM) -> SessionRecord:
        initial = await self._ref_for(row.latest_initial_artifact_id)
        final = await self._ref_for(row.latest_final_artifact_id)
        return session_from_row(row, latest_initial=initial, latest_final=final)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _artifacts_for_run(self, run_id: str) -> tuple[ArtifactRef, ...]:
        stmt = (
            select(ArtifactORM)
            .where(ArtifactORM.run_id == run_id)
            .order_by(
                ArtifactORM.run_order.asc(),
                ArtifactORM.created_at.asc(),
                ArtifactORM.artifact_id.asc(),
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(artifact_ref_from_row(r) for r in rows)

    async def create(self, run: RunRecord) -> RunRecord:
        values = run_to_row_values(run)
        row = RunORM(created_at=run.created_at or utc_now(), **values)
        self._session.add(row)
        await _flush(self._session)
        artifacts = await self._artifacts_for_run(row.run_id)
        return run_from_row(row, artifacts=artifacts)

    async def get(self, run_id: RunId) -> RunRecord | None:
        row = await self._session.get(RunORM, run_id)
        if row is None:
            return None
        artifacts = await self._artifacts_for_run(row.run_id)
        return run_from_row(row, artifacts=artifacts)

    async def require(self, run_id: RunId) -> RunRecord:
        record = await self.get(run_id)
        if record is None:
            raise PersistenceNotFoundError("run not found")
        return record

    async def list_for_session(
        self, session_id: SessionId, *, limit: int | None = None
    ) -> list[RunRecord]:
        _check_limit(limit)
        stmt = (
            select(RunORM)
            .where(RunORM.session_id == session_id)
            .order_by(RunORM.created_at.desc(), RunORM.run_id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        result: list[RunRecord] = []
        for r in rows:
            artifacts = await self._artifacts_for_run(r.run_id)
            result.append(run_from_row(r, artifacts=artifacts))
        return result

    async def update(self, run: RunRecord) -> RunRecord:
        row = await self._session.get(RunORM, run.run_id)
        if row is None:
            raise PersistenceNotFoundError("run not found")
        values = run_to_row_values(run)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = utc_now()
        await _flush(self._session)
        artifacts = await self._artifacts_for_run(row.run_id)
        return run_from_row(row, artifacts=artifacts)


# ---------------------------------------------------------------------------
# Browser contexts
# ---------------------------------------------------------------------------


class BrowserContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _ref_for(self, artifact_id: str | None) -> ArtifactRef | None:
        if artifact_id is None:
            return None
        row = await self._session.get(ArtifactORM, artifact_id)
        if row is None:
            return None
        return artifact_ref_from_row(row)

    async def create(self, context: BrowserContextRecord) -> BrowserContextRecord:
        values = context_to_row_values(context)
        row = BrowserContextORM(
            created_at=context.created_at or utc_now(), **values
        )
        self._session.add(row)
        await _flush(self._session)
        return await self._rehydrate(row)

    async def get(self, context_id: ContextId) -> BrowserContextRecord | None:
        row = await self._session.get(BrowserContextORM, context_id)
        if row is None:
            return None
        return await self._rehydrate(row)

    async def require(self, context_id: ContextId) -> BrowserContextRecord:
        record = await self.get(context_id)
        if record is None:
            raise PersistenceNotFoundError("browser context not found")
        return record

    async def list_for_run(
        self, run_id: RunId, *, limit: int | None = None
    ) -> list[BrowserContextRecord]:
        _check_limit(limit)
        stmt = (
            select(BrowserContextORM)
            .where(BrowserContextORM.run_id == run_id)
            .order_by(
                BrowserContextORM.created_at.asc(),
                BrowserContextORM.context_id.asc(),
            )
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [await self._rehydrate(r) for r in rows]

    async def update(self, context: BrowserContextRecord) -> BrowserContextRecord:
        row = await self._session.get(BrowserContextORM, context.context_id)
        if row is None:
            raise PersistenceNotFoundError("browser context not found")
        values = context_to_row_values(context)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = utc_now()
        await _flush(self._session)
        return await self._rehydrate(row)

    async def _rehydrate(self, row: BrowserContextORM) -> BrowserContextRecord:
        initial = await self._ref_for(row.initial_storage_artifact_id)
        final = await self._ref_for(row.final_storage_artifact_id)
        return context_from_row(row, initial=initial, final=final)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        ref: ArtifactRef,
        *,
        session_id: SessionId | None = None,
        run_id: RunId | None = None,
        run_order: int | None = None,
    ) -> ArtifactRef:
        if run_id is not None and run_order is None:
            raise PersistenceIntegrityError(
                "run_order is required when run_id is provided"
            )
        values = artifact_ref_to_row_values(
            ref, session_id=session_id, run_id=run_id, run_order=run_order
        )
        row = ArtifactORM(created_at=utc_now(), **values)
        self._session.add(row)
        await _flush(self._session)
        return artifact_ref_from_row(row)

    async def get(self, artifact_id: ArtifactId) -> ArtifactRef | None:
        row = await self._session.get(ArtifactORM, artifact_id)
        if row is None:
            return None
        return artifact_ref_from_row(row)

    async def require(self, artifact_id: ArtifactId) -> ArtifactRef:
        record = await self.get(artifact_id)
        if record is None:
            raise PersistenceNotFoundError("artifact not found")
        return record

    async def list_for_run(self, run_id: RunId) -> list[ArtifactRef]:
        stmt = (
            select(ArtifactORM)
            .where(ArtifactORM.run_id == run_id)
            .order_by(
                ArtifactORM.run_order.asc(),
                ArtifactORM.created_at.asc(),
                ArtifactORM.artifact_id.asc(),
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [artifact_ref_from_row(r) for r in rows]

    async def list_for_session(
        self, session_id: SessionId, *, limit: int | None = None
    ) -> list[ArtifactRef]:
        _check_limit(limit)
        stmt = (
            select(ArtifactORM)
            .where(ArtifactORM.session_id == session_id)
            .order_by(ArtifactORM.created_at.desc(), ArtifactORM.artifact_id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [artifact_ref_from_row(r) for r in rows]

    async def list_by_type(
        self, artifact_type: ArtifactType, *, limit: int | None = None
    ) -> list[ArtifactRef]:
        _check_limit(limit)
        stmt = (
            select(ArtifactORM)
            .where(ArtifactORM.artifact_type == artifact_type)
            .order_by(ArtifactORM.created_at.desc(), ArtifactORM.artifact_id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [artifact_ref_from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: SessionHealthRecord) -> SessionHealthRecord:
        values = health_to_row_values(record)
        row = HealthRecordORM(created_at=record.created_at or utc_now(), **values)
        self._session.add(row)
        await _flush(self._session)
        return health_from_row(row)

    async def latest_for_session(
        self, session_id: SessionId
    ) -> SessionHealthRecord | None:
        stmt = (
            select(HealthRecordORM)
            .where(HealthRecordORM.session_id == session_id)
            .order_by(HealthRecordORM.created_at.desc(), HealthRecordORM.id.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return health_from_row(row)

    async def list_for_session(
        self, session_id: SessionId, *, limit: int | None = None
    ) -> list[SessionHealthRecord]:
        _check_limit(limit)
        stmt = (
            select(HealthRecordORM)
            .where(HealthRecordORM.session_id == session_id)
            .order_by(HealthRecordORM.created_at.desc(), HealthRecordORM.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [health_from_row(r) for r in rows]
