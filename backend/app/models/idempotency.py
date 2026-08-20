"""Persistence model for scoped HTTP idempotency state."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utc_now


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        Index(
            "uq_idempotency_user_route_key",
            "user_id",
            "route",
            "idempotency_key",
            unique=True,
        ),
        CheckConstraint(
            "response_json IS NULL OR JSON_STORAGE_SIZE(response_json) <= 16384",
            name="ck_idempotency_response_json_size",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
