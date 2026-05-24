"""Security / redaction row-scan tests (spec 19.12)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import text
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
    HealthRepository,
    PersistenceError,
    PersistenceSecurityError,
    ProfileRepository,
    RunRepository,
    SessionRepository,
    make_alembic_config,
    sanitize_database_url,
)

from tests.persistence._factories import (
    SESSION_ID,
    artifact_ref,
    health_record,
    profile_record,
    run_record,
    session_record,
)

_FORBIDDEN_SAMPLES = (
    "raw-token-123",
    "session-cookie-value",
    "Bearer raw-secret",
    "proxy-password-123",
    "refresh-token-abc",
)

_ALL_TABLES = (
    "profiles",
    "sessions",
    "runs",
    "browser_contexts",
    "artifacts",
    "health_records",
)


async def _seed_session(session: AsyncSession, tmp_path: Path) -> None:
    await ProfileRepository(session, data_dir=tmp_path / "data").create(
        profile_record(tmp_path / "data")
    )
    await SessionRepository(session).create(session_record())


async def _scan_all_rows(session: AsyncSession) -> str:
    chunks: list[str] = []
    for table in _ALL_TABLES:
        rows = (await session.execute(text(f"SELECT * FROM {table}"))).mappings().all()
        for row in rows:
            chunks.append(str(dict(row)))
    return "\n".join(chunks)


async def test_run_metadata_access_token_redacted(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record(metadata={"access_token": "raw-token-123"})
    async with session.begin():
        await _seed_session(session, tmp_path)
        await RunRepository(session).create(run)
    dump = await _scan_all_rows(session)
    assert "raw-token-123" not in dump


async def test_nested_metadata_secrets_redacted(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = run_record(
        metadata={"outer": {"refresh_token": "refresh-token-abc", "ok": "v"}}
    )
    async with session.begin():
        await _seed_session(session, tmp_path)
        created = await RunRepository(session).create(run)
    assert "refresh-token-abc" not in str(created.metadata)
    dump = await _scan_all_rows(session)
    assert "refresh-token-abc" not in dump


async def test_health_reason_redacted(
    session: AsyncSession, tmp_path: Path
) -> None:
    rec = health_record(reason="token=raw-token-123")
    async with session.begin():
        await _seed_session(session, tmp_path)
        await HealthRepository(session).create(rec)
    dump = await _scan_all_rows(session)
    assert "raw-token-123" not in dump


async def test_rows_lack_proxy_password(
    session: AsyncSession, tmp_path: Path
) -> None:
    # Proxy password config must be rejected, never stored.
    bad = SessionRecord(
        session_id="sess_beta_default00",
        name="s",
        profile_id="prof_alpha_default",
        config=SessionConfig(
            launch=BrowserLaunchConfig(
                engine_name="mock",
                proxy=ProxyConfig(
                    server="http://p", password=SecretStr("proxy-password-123")
                ),
            ),
            context=BrowserContextConfig(),
        ),
    )
    with pytest.raises(PersistenceSecurityError):
        async with session.begin():
            await _seed_session(session, tmp_path)
            await SessionRepository(session).create(bad)


async def test_rows_lack_forbidden_samples_central_scan(
    session: AsyncSession, tmp_path: Path
) -> None:
    # Persist a broad mix of metadata that contains every forbidden sample as
    # values; all must be redacted at the storage boundary.
    run = run_record(
        metadata={
            "access_token": "raw-token-123",
            "cookie": "session-cookie-value",
            "authorization": "Bearer raw-secret",
            "refresh_token": "refresh-token-abc",
        }
    )
    async with session.begin():
        await _seed_session(session, tmp_path)
        await RunRepository(session).create(run)
        await ArtifactRepository(session).create(
            artifact_ref(), session_id=SESSION_ID
        )
        await HealthRepository(session).create(
            health_record(reason="password=proxy-password-123")
        )
    dump = await _scan_all_rows(session)
    for sample in _FORBIDDEN_SAMPLES:
        assert sample not in dump, f"forbidden sample leaked: {sample}"


async def test_error_wrapping_no_sql_or_db_url(
    session: AsyncSession, tmp_path: Path
) -> None:
    # Trigger a duplicate-key integrity error and inspect the message.
    from sightstalker.persistence import PersistenceIntegrityError

    async with session.begin():
        await _seed_session(session, tmp_path)
        await RunRepository(session).create(run_record())
    try:
        async with session.begin():
            await RunRepository(session).create(run_record())
    except PersistenceIntegrityError as exc:
        msg = str(exc)
        assert "INSERT" not in msg.upper()
        assert "sqlite+aiosqlite" not in msg
    else:  # pragma: no cover
        pytest.fail("expected PersistenceIntegrityError")


def test_db_url_fake_password_absent_from_exception() -> None:
    url = "postgresql+asyncpg://admin:proxy-password-123@db.internal/app"
    # make_alembic_config sets the URL but must never echo it raw on error;
    # sanitize must strip the password.
    cfg = make_alembic_config(url)
    assert cfg is not None
    assert "proxy-password-123" not in sanitize_database_url(url)


def test_persistence_error_is_runtimeerror() -> None:
    assert issubclass(PersistenceError, RuntimeError)


async def test_artifact_payload_text_absent(
    session: AsyncSession, tmp_path: Path
) -> None:
    # Artifact rows store only metadata; the relative path/hash, never payloads.
    async with session.begin():
        await ArtifactRepository(session).create(artifact_ref())
    rows = (
        (await session.execute(text("SELECT * FROM artifacts"))).mappings().all()
    )
    for row in rows:
        keys = {k.lower() for k in row.keys()}
        assert "payload" not in keys
        assert "content" not in keys
        assert "blob" not in keys
