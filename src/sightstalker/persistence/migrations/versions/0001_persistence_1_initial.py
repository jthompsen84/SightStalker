"""persistence-1 initial schema

Revision ID: 0001_persistence_1_initial
Revises:
Create Date: 2026-05-24

Creates the metadata-only schema: profiles, sessions, runs, browser_contexts,
artifacts, and health_records. All runtime foreign keys use RESTRICT delete
behavior (no cascade). JSON-bearing columns are Text holding canonical JSON.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_persistence_1_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("profile_dir", sa.String(length=1024), nullable=False),
        sa.Column("fingerprint_profile_id", sa.String(length=128), nullable=True),
        sa.Column("proxy_profile_id", sa.String(length=128), nullable=True),
        sa.Column("health_status", sa.String(length=32), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_profiles_name_nonempty"),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_index("ix_profiles_created_at", "profiles", ["created_at"])

    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("hash_algorithm", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("run_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifacts_size_nonneg"),
        sa.CheckConstraint(
            "(run_id IS NULL) OR (run_order IS NOT NULL)",
            name="ck_artifacts_run_order_present",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("artifact_id"),
        sa.UniqueConstraint("run_id", "run_order", name="uq_artifacts_run_order"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_session_id", "artifacts", ["session_id"])
    op.create_index("ix_artifacts_type", "artifacts", ["artifact_type"])
    op.create_index("ix_artifacts_created_at", "artifacts", ["created_at"])

    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column(
            "latest_initial_artifact_id", sa.String(length=128), nullable=True
        ),
        sa.Column("latest_final_artifact_id", sa.String(length=128), nullable=True),
        sa.Column("health_status", sa.String(length=32), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_sessions_name_nonempty"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.profile_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["latest_initial_artifact_id"],
            ["artifacts.artifact_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["latest_final_artifact_id"],
            ["artifacts.artifact_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_sessions_profile_id", "sessions", ["profile_id"])
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_url", sa.String(length=2048), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message_redacted", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_runs_session_id", "runs", ["session_id"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])

    op.create_table(
        "browser_contexts",
        sa.Column("context_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column(
            "initial_storage_artifact_id", sa.String(length=128), nullable=True
        ),
        sa.Column(
            "final_storage_artifact_id", sa.String(length=128), nullable=True
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["initial_storage_artifact_id"],
            ["artifacts.artifact_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["final_storage_artifact_id"],
            ["artifacts.artifact_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("context_id"),
    )
    op.create_index("ix_browser_contexts_run_id", "browser_contexts", ["run_id"])
    op.create_index(
        "ix_browser_contexts_session_id", "browser_contexts", ["session_id"]
    )
    op.create_index(
        "ix_browser_contexts_created_at", "browser_contexts", ["created_at"]
    )

    op.create_table(
        "health_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("last_successful_run_id", sa.String(length=128), nullable=True),
        sa.Column("last_failed_run_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.session_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["last_successful_run_id"], ["runs.run_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["last_failed_run_id"], ["runs.run_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_health_records_session_id", "health_records", ["session_id"]
    )
    op.create_index(
        "ix_health_records_created_at", "health_records", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("health_records")
    op.drop_table("browser_contexts")
    op.drop_table("runs")
    op.drop_table("sessions")
    op.drop_table("artifacts")
    op.drop_table("profiles")
