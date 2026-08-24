"""Create scan session and keyframe tables.

Revision ID: 0003_scan_tables
Revises: 0002_binary_identity_collations
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003_scan_tables"
down_revision: str | None = "0002_binary_identity_collations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_sessions",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("detected_fields", mysql.JSON(), nullable=False),
        sa.Column("conflicts", mysql.JSON(), nullable=False),
        sa.Column("missing_fields", mysql.JSON(), nullable=False),
        sa.Column("next_guidance", sa.String(length=255), nullable=False),
        sa.Column("mock_scenario", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scan_sessions_user_status",
        "scan_sessions",
        ["user_id", "status"],
        unique=False,
    )
    op.create_table(
        "scan_images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scan_session_id", sa.CHAR(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("perceptual_hash", sa.String(length=16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("brightness", sa.Float(), nullable=False),
        sa.Column("sharpness", sa.Float(), nullable=False),
        sa.Column("analysis_status", sa.String(length=16), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["scan_session_id"], ["scan_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scan_images_session_status",
        "scan_images",
        ["scan_session_id", "analysis_status"],
        unique=False,
    )
    op.create_index(
        "uq_scan_images_session_sha256",
        "scan_images",
        ["scan_session_id", "sha256"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_food_records_scan_session_id",
        "food_records",
        "scan_sessions",
        ["scan_session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_food_records_scan_session_id", "food_records", type_="foreignkey"
    )
    op.drop_table("scan_images")
    op.drop_table("scan_sessions")
