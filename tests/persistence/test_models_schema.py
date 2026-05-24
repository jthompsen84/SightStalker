"""ORM schema tests (spec 19.3)."""

from __future__ import annotations

from sqlalchemy import inspect

from sightstalker.persistence.models import (
    ArtifactORM,
    Base,
    BrowserContextORM,
    HealthRecordORM,
    ProfileORM,
    RunORM,
    SessionORM,
)

_TABLES = {
    "profiles",
    "sessions",
    "runs",
    "browser_contexts",
    "artifacts",
    "health_records",
}

_FORBIDDEN_SUBSTRINGS = (
    "cookie",
    "storage_state",
    "payload",
    "content",
    "bytes",  # note: size_bytes is allowed; handled explicitly below
    "blob",
    "screenshot",
    "trace_payload",
    "artifact_payload",
    "authorization",
    "refresh_token",
    "access_token",
    "password",
    "passphrase",
    "client_secret",
    "secret",
    "token",
)

# Columns explicitly allowed despite matching a forbidden substring.
_ALLOWED_EXACT = {"size_bytes", "error_message_redacted"}


def test_tables_exist() -> None:
    assert _TABLES <= set(Base.metadata.tables.keys())


def test_primary_keys_exist() -> None:
    for table_name in _TABLES:
        table = Base.metadata.tables[table_name]
        assert len(table.primary_key.columns) >= 1


def test_foreign_keys_exist() -> None:
    sessions = Base.metadata.tables["sessions"]
    runs = Base.metadata.tables["runs"]
    contexts = Base.metadata.tables["browser_contexts"]
    artifacts = Base.metadata.tables["artifacts"]
    health = Base.metadata.tables["health_records"]
    assert len(sessions.foreign_keys) >= 1
    assert len(runs.foreign_keys) >= 1
    assert len(contexts.foreign_keys) >= 2
    assert len(artifacts.foreign_keys) >= 2
    assert len(health.foreign_keys) >= 1


def test_foreign_keys_are_restrictive() -> None:
    for table_name in _TABLES:
        table = Base.metadata.tables[table_name]
        for fk in table.foreign_keys:
            assert fk.ondelete == "RESTRICT", (
                f"{table_name}.{fk.parent.name} must use RESTRICT"
            )


def test_indexes_exist() -> None:
    runs = Base.metadata.tables["runs"]
    index_cols = {tuple(c.name for c in idx.columns) for idx in runs.indexes}
    assert ("session_id",) in index_cols or any(
        "session_id" in cols for cols in index_cols
    )


def test_unique_run_order_constraint() -> None:
    from sqlalchemy import UniqueConstraint

    artifacts = Base.metadata.tables["artifacts"]
    uniques = [
        c for c in artifacts.constraints if isinstance(c, UniqueConstraint)
    ]
    names = {tuple(col.name for col in u.columns) for u in uniques}
    assert ("run_id", "run_order") in names


def test_check_constraints_exist() -> None:
    artifacts = Base.metadata.tables["artifacts"]
    check_names = {
        c.name
        for c in artifacts.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_artifacts_size_nonneg" in check_names
    assert "ck_artifacts_run_order_present" in check_names


def test_no_forbidden_payload_columns() -> None:
    for table_name in _TABLES:
        table = Base.metadata.tables[table_name]
        for col in table.columns:
            name = col.name.lower()
            if name in _ALLOWED_EXACT:
                continue
            for forbidden in _FORBIDDEN_SUBSTRINGS:
                assert forbidden not in name, (
                    f"{table_name}.{col.name} contains forbidden substring "
                    f"'{forbidden}'"
                )


def test_profiles_has_no_active_lock_path() -> None:
    cols = {c.name for c in Base.metadata.tables["profiles"].columns}
    assert "active_lock_path" not in cols


def test_artifacts_stores_relative_path_not_absolute() -> None:
    cols = {c.name for c in Base.metadata.tables["artifacts"].columns}
    assert "relative_path" in cols
    assert "absolute_path" not in cols
    assert "path" not in cols


def test_runs_stores_redacted_error_not_raw() -> None:
    cols = {c.name for c in Base.metadata.tables["runs"].columns}
    assert "error_message_redacted" in cols
    assert "error_message" not in cols


def test_no_mapped_attribute_named_metadata() -> None:
    for orm in (
        ProfileORM,
        SessionORM,
        RunORM,
        BrowserContextORM,
        ArtifactORM,
        HealthRecordORM,
    ):
        mapper = inspect(orm)
        attr_names = {attr.key for attr in mapper.column_attrs}
        assert "metadata" not in attr_names


def test_timestamps_present() -> None:
    for table_name in _TABLES:
        cols = {c.name for c in Base.metadata.tables[table_name].columns}
        assert "created_at" in cols
        assert "updated_at" in cols
