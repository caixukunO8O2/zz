"""Core user, food, and preservation-rule persistence models."""

from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(
        String(128, collation="utf8mb4_bin"), nullable=False, unique=True
    )
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    foods: Mapped[list["FoodRecord"]] = relationship(back_populates="user")


class FoodRecord(Base):
    __tablename__ = "food_records"
    __table_args__ = (
        Index(
            "ix_food_records_user_lifecycle_consume_by",
            "user_id",
            "lifecycle_status",
            "recommended_consume_by",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scan_session_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    food_name: Mapped[str] = mapped_column(String(128), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    declared_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_on: Mapped[date] = mapped_column(Date, nullable=False)
    storage_type: Mapped[str] = mapped_column(String(16), nullable=False)
    recommended_consume_by: Mapped[date] = mapped_column(Date, nullable=False)
    date_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    user: Mapped[User] = relationship(back_populates="foods")


class PreservationRuleModel(Base):
    __tablename__ = "preservation_rules"
    __table_args__ = (
        Index("uq_preservation_rules_name_version", "food_name", "rule_version", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    food_name: Mapped[str] = mapped_column(String(128), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    room_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chilled_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frozen_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_note: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
