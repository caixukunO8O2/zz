"""Use cases for creating, reading, and cancelling scan sessions."""

from datetime import timedelta

from app.core.errors import APIError
from app.domain.scans import ScanStatus
from app.models.entities import User
from app.models.scan_entities import ScanSession
from app.repositories.scans import ScanRepository
from app.schemas.scans import ScanImageRead, ScanSessionCreate, ScanSessionRead

UNFINISHED_SCAN_STATUSES = {
    ScanStatus.SCANNING,
    ScanStatus.ANALYZING,
    ScanStatus.NEEDS_INPUT,
    ScanStatus.READY,
    ScanStatus.FAILED,
}


class ScanService:
    def __init__(self, repository: ScanRepository, *, app_mode: str, now) -> None:
        self._repository = repository
        self._app_mode = app_mode
        self._now = now

    async def create(self, user: User, payload: ScanSessionCreate) -> ScanSession:
        if payload.mock_scenario is not None and self._app_mode != "mock":
            raise APIError(422, "mock_scenario_unavailable", "当前模式不支持模拟场景")
        return await self._repository.create(
            user.id,
            expires_at=self._now() + timedelta(hours=24),
            mock_scenario=payload.mock_scenario,
        )

    async def get_for_user(self, scan_session_id: str, user_id: int) -> ScanSession:
        record = await self._repository.get_for_user(scan_session_id, user_id)
        if record is None:
            raise APIError(404, "scan_session_not_found", "没有找到本次扫描")
        return record

    async def cancel(self, scan_session_id: str, user_id: int) -> ScanSession:
        record = await self._repository.get_for_user(
            scan_session_id, user_id, for_update=True
        )
        if record is None:
            raise APIError(404, "scan_session_not_found", "没有找到本次扫描")
        status = ScanStatus(record.status)
        if status is ScanStatus.CANCELLED:
            return record
        if status not in UNFINISHED_SCAN_STATUSES:
            raise APIError(409, "invalid_scan_transition", "当前扫描状态不能取消")
        return await self._repository.set_status(record, ScanStatus.CANCELLED)

    @staticmethod
    def present(record: ScanSession) -> ScanSessionRead:
        return ScanSessionRead(
            id=record.id,
            status=ScanStatus(record.status),
            detected_fields=record.detected_fields,
            conflicts=record.conflicts,
            missing_fields=record.missing_fields,
            next_guidance=record.next_guidance,
            expires_at=record.expires_at,
            images=[
                ScanImageRead(
                    id=image.id,
                    purpose=image.purpose,
                    analysis_status=image.analysis_status,
                )
                for image in record.images
            ],
        )

