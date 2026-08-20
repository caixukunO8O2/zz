"""Create core persistence tables and seed preservation rules.

Revision ID: 0001_core_tables
Revises:
Create Date: 2026-08-20
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

from app.domain.preservation import load_seed_rules

revision: str = "0001_core_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_PATH = Path(__file__).parents[2] / "app" / "seed" / "preservation_rules.csv"


def _seed_preservation_rules() -> None:
    """Upsert the validated CSV seed by its (food_name, rule_version) key."""
    rules_table = sa.table(
        "preservation_rules",
        sa.column("food_name", sa.String(128)),
        sa.column("aliases", mysql.JSON()),
        sa.column("category", sa.String(32)),
        sa.column("room_days", sa.Integer()),
        sa.column("chilled_days", sa.Integer()),
        sa.column("frozen_days", sa.Integer()),
        sa.column("source_note", sa.Text()),
        sa.column("rule_version", sa.String(32)),
        sa.column("enabled", sa.Boolean()),
    )
    rows = [
        {
            "food_name": rule.name,
            "aliases": list(rule.aliases),
            "category": rule.category,
            "room_days": rule.room_days,
            "chilled_days": rule.chilled_days,
            "frozen_days": rule.frozen_days,
            "source_note": rule.source_note,
            "rule_version": rule.version,
            "enabled": True,
        }
        for rule in load_seed_rules(SEED_PATH)
    ]
    statement = mysql.insert(rules_table).values(rows)
    statement = statement.on_duplicate_key_update(
        aliases=statement.inserted.aliases,
        category=statement.inserted.category,
        room_days=statement.inserted.room_days,
        chilled_days=statement.inserted.chilled_days,
        frozen_days=statement.inserted.frozen_days,
        source_note=statement.inserted.source_note,
        enabled=statement.inserted.enabled,
    )
    op.get_bind().execute(statement)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("openid", sa.String(length=128), nullable=False),
        sa.Column("nickname", sa.String(length=64), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("openid", name="uq_users_openid"),
    )
    op.create_table(
        "preservation_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("food_name", sa.String(length=128), nullable=False),
        sa.Column("aliases", mysql.JSON(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("room_days", sa.Integer(), nullable=True),
        sa.Column("chilled_days", sa.Integer(), nullable=True),
        sa.Column("frozen_days", sa.Integer(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_preservation_rules_name_version",
        "preservation_rules",
        ["food_name", "rule_version"],
        unique=True,
    )
    op.create_table(
        "food_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("scan_session_id", sa.CHAR(length=36), nullable=True),
        sa.Column("food_name", sa.String(length=128), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=512), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("declared_expiry_date", sa.Date(), nullable=True),
        sa.Column("shelf_life_days", sa.Integer(), nullable=True),
        sa.Column("added_on", sa.Date(), nullable=False),
        sa.Column("storage_type", sa.String(length=16), nullable=False),
        sa.Column("recommended_consume_by", sa.Date(), nullable=False),
        sa.Column("date_basis", sa.String(length=40), nullable=False),
        sa.Column("confidence_summary", mysql.JSON(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_food_records_user_lifecycle_consume_by",
        "food_records",
        ["user_id", "lifecycle_status", "recommended_consume_by"],
        unique=False,
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_resource_id", sa.String(length=64), nullable=True),
        sa.Column("response_json", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "response_json IS NULL OR JSON_STORAGE_SIZE(response_json) <= 16384",
            name="ck_idempotency_response_json_size",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_idempotency_user_route_key",
        "idempotency_records",
        ["user_id", "route", "idempotency_key"],
        unique=True,
    )
    _seed_preservation_rules()


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("food_records")
    op.drop_table("preservation_rules")
    op.drop_table("users")
