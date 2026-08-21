"""User-scoped scan-session persistence operations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select
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

    async def commit(self) -> None:
        await self._session.commit()

    async def delete_image(self, image: ScanImage) -> None:
        await self._session.execute(delete(ScanImage).where(ScanImage.id == image.id))
        await self._session.flush()

    async def get_image(self, scan_image_id: int) -> ScanImage | None:
        return await self._session.get(ScanImage, scan_image_id)

    async def lock_for_analysis(self, scan_session_id: str) -> ScanSession | None:
        return await self._session.scalar(
            select(ScanSession)
            .where(ScanSession.id == scan_session_id)
            .options(selectinload(ScanSession.images))
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def set_image_status(
        self, image: ScanImage, status: str, failure_code: str | None = None
    ) -> None:
        image.analysis_status = status
        image.failure_code = failure_code
        image.updated_at = utc_now()
        await self._session.flush()

    async def save_analysis(
        self,
        record: ScanSession,
        *,
        status: str,
        detected_fields: dict[str, object],
        conflicts: list[dict[str, object]],
        missing_fields: list[str],
        next_guidance: str,
    ) -> None:
        record.status = status
        record.detected_fields = detected_fields
        record.conflicts = conflicts
        record.missing_fields = missing_fields
        record.next_guidance = next_guidance
        record.updated_at = utc_now()
        await self._session.flush()
