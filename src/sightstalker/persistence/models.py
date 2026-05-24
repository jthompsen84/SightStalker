"""
sightstalker.persistence.models — SQLAlchemy 2.x typed ORM models.

Metadata-only schema for profiles, sessions, runs, browser contexts, artifact
references, and health records. No raw payloads, secrets, or absolute paths are
ever mapped here. JSON-bearing columns use ``Text`` with canonical JSON encoded
at the serialization boundary, not SQLAlchemy ``JSON``, for deterministic
SQLite behavior and row scanning.

No mapped attribute is named ``metadata`` (it collides with
``DeclarativeBase.metadata``); the run metadata column is ``metadata_json``.
All runtime foreign keys use ``RESTRICT`` delete behavior — no cascade.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_ID_LEN = 128
_NAME_LEN = 255
_STATUS_LEN = 32
_PATH_LEN = 1024
_SHA_LEN = 64
_MIME_LEN = 128
_URL_LEN = 2048


class Base(DeclarativeBase):
    """Declarative base for all persistence ORM models."""


class TimestampMixin:
    """Shared created/updated timestamp columns (UTC, tz-aware)."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class ProfileORM(TimestampMixin, Base):
    __tablename__ = "profiles"

    profile_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    name: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False)
    profile_dir: Mapped[str] = mapped_column(String(_PATH_LEN), nullable=False)
    fingerprint_profile_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN), nullable=True
    )
    proxy_profile_id: Mapped[str | None] = mapped_column(String(_ID_LEN), nullable=True)
    health_status: Mapped[str] = mapped_column(String(_STATUS_LEN), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_profiles_name_nonempty"),
        Index("ix_profiles_created_at", "created_at"),
    )


class SessionORM(TimestampMixin, Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    name: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False)
    profile_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        ForeignKey("profiles.profile_id", ondelete="RESTRICT"),
        nullable=False,
    )
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    latest_initial_artifact_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"),
        nullable=True,
    )
    latest_final_artifact_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"),
        nullable=True,
    )
    health_status: Mapped[str] = mapped_column(String(_STATUS_LEN), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_sessions_name_nonempty"),
        Index("ix_sessions_profile_id", "profile_id"),
        Index("ix_sessions_created_at", "created_at"),
    )


class RunORM(TimestampMixin, Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        ForeignKey("sessions.session_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(_STATUS_LEN), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_url: Mapped[str | None] = mapped_column(String(_URL_LEN), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(_NAME_LEN), nullable=True)
    error_message_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_runs_session_id", "session_id"),
        Index("ix_runs_created_at", "created_at"),
    )


class BrowserContextORM(TimestampMixin, Base):
    __tablename__ = "browser_contexts"

    context_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        ForeignKey("sessions.session_id", ondelete="RESTRICT"),
        nullable=False,
    )
    initial_storage_artifact_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"),
        nullable=True,
    )
    final_storage_artifact_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_browser_contexts_run_id", "run_id"),
        Index("ix_browser_contexts_session_id", "session_id"),
        Index("ix_browser_contexts_created_at", "created_at"),
    )


class ArtifactORM(TimestampMixin, Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    artifact_type: Mapped[str] = mapped_column(String(_STATUS_LEN), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(_PATH_LEN), nullable=False)
    sha256: Mapped[str] = mapped_column(String(_SHA_LEN), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(_MIME_LEN), nullable=True)
    hash_algorithm: Mapped[str] = mapped_column(String(_STATUS_LEN), nullable=False)
    session_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("sessions.session_id", ondelete="RESTRICT"),
        nullable=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=True,
    )
    run_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "run_order", name="uq_artifacts_run_order"),
        CheckConstraint("size_bytes >= 0", name="ck_artifacts_size_nonneg"),
        CheckConstraint(
            "(run_id IS NULL) OR (run_order IS NOT NULL)",
            name="ck_artifacts_run_order_present",
        ),
        Index("ix_artifacts_run_id", "run_id"),
        Index("ix_artifacts_session_id", "session_id"),
        Index("ix_artifacts_type", "artifact_type"),
        Index("ix_artifacts_created_at", "created_at"),
    )


class HealthRecordORM(TimestampMixin, Base):
    __tablename__ = "health_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        ForeignKey("sessions.session_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(_STATUS_LEN), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_run_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=True,
    )
    last_failed_run_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN),
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_health_records_session_id", "session_id"),
        Index("ix_health_records_created_at", "created_at"),
    )
