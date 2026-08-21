"""User-scoped scan-session persistence operations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.scans import (
    INITIAL_GUIDANCE,
    INITIAL_MISSING_FIELDS,
    ImagePurpose,
    ScanStatus,
)
from app.models.base import utc_now
from app.models.scan_entities import ScanImage, ScanSession


@dataclass(frozen=True, slots=True)
class ScanImageCreateData:
    purpose: ImagePurpose
    storage_path: str
    content_type: str
    sha256: str
    perceptual_hash: str
    width: int
    height: int
    brightness: float
    sharpness: float


class ScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        *,
        expires_at: datetime,
        mock_scenario: str | None,
    ) -> ScanSession:
        record = ScanSession(
            id=str(uuid4()),
            user_id=user_id,
            status=ScanStatus.SCANNING.value,
            detected_fields={},
            conflicts=[],
            missing_fields=list(INITIAL_MISSING_FIELDS),
            next_guidance=INITIAL_GUIDANCE,
            mock_scenario=mock_scenario,
            expires_at=expires_at,
            images=[],
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_for_user(
        self, scan_session_id: str, user_id: int, *, for_update: bool = False
    ) -> ScanSession | None:
        statement = (
            select(ScanSession)
            .where(
                ScanSession.id == scan_session_id,
                ScanSession.user_id == user_id,
            )
            .options(selectinload(ScanSession.images))
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return await self._session.scalar(statement)

    async def set_status(
        self, record: ScanSession, status: ScanStatus
    ) -> ScanSession:
        record.status = status.value
        record.updated_at = utc_now()
        await self._session.flush()
        return record

    async def add_image(
        self, record: ScanSession, data: ScanImageCreateData
    ) -> ScanImage:
        image = ScanImage(
            scan_session_id=record.id,
            purpose=data.purpose.value,
            storage_path=data.storage_path,
            content_type=data.content_type,
            sha256=data.sha256,
            perceptual_hash=data.perceptual_hash,
            width=data.width,
            height=data.height,
            brightness=data.brightness,
            sharpness=data.sharpness,
            analysis_status="queued",
        )
        record.images.append(image)
        await self._session.flush()
        return image
