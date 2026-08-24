"""Ensure one food record is created per scan session.

Revision ID: 0004_unique_food_scan_session
Revises: 0003_scan_tables
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_unique_food_scan_session"
down_revision: str | None = "0003_scan_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_food_records_scan_session_id",
        "food_records",
        ["scan_session_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_food_records_scan_session_id", table_name="food_records")

