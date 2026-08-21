"""Use case-sensitive collations for external and idempotency identities.

Revision ID: 0002_binary_identity_collations
Revises: 0001_core_tables
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002_binary_identity_collations"
down_revision: str | None = "0001_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_identity_collation(collation: str) -> None:
    op.alter_column(
        "users",
        "openid",
        existing_type=mysql.VARCHAR(length=128),
        type_=mysql.VARCHAR(length=128, collation=collation),
        existing_nullable=False,
    )
    for column_name in ("route", "idempotency_key"):
        op.alter_column(
            "idempotency_records",
            column_name,
            existing_type=mysql.VARCHAR(length=255),
            type_=mysql.VARCHAR(length=255, collation=collation),
            existing_nullable=False,
        )


def upgrade() -> None:
    _set_identity_collation("utf8mb4_bin")


def downgrade() -> None:
    _set_identity_collation("utf8mb4_0900_ai_ci")
