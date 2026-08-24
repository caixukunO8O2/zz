"""Persistence models for scan sessions and accepted keyframes."""

from datetime import datetime

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utc_now


class ScanSession(Base):
    __tablename__ = "scan_sessions"
    __table_args__ = (Index("ix_scan_sessions_user_status", "user_id", "status"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    detected_fields: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    next_guidance: Mapped[str] = mapped_column(String(255), nullable=False)
    mock_scenario: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    images: Mapped[list["ScanImage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ScanImage.id",
    )


class ScanImage(Base):
    __tablename__ = "scan_images"
    __table_args__ = (
        Index("ix_scan_images_session_status", "scan_session_id", "analysis_status"),
        Index("uq_scan_images_session_sha256", "scan_session_id", "sha256", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scan_session_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("scan_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    perceptual_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    brightness: Mapped[float] = mapped_column(Float, nullable=False)
    sharpness: Mapped[float] = mapped_column(Float, nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    session: Mapped[ScanSession] = relationship(back_populates="images")

