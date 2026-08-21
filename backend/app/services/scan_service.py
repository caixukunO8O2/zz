"""Use cases for creating, reading, and cancelling scan sessions."""

from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.errors import APIError
from app.domain.scans import ImagePurpose, ScanStatus
from app.models.entities import User
from app.models.scan_entities import ScanSession
from app.ports.scan_queue import ScanQueuePort
from app.ports.storage import StoragePort
from app.repositories.scans import ScanImageCreateData, ScanRepository
from app.schemas.scans import (
    ScanFrameRead,
    ScanImageRead,
    ScanSessionCreate,
    ScanSessionRead,
)
from app.services.image_quality import assess_image, hamming_distance

UNFINISHED_SCAN_STATUSES = {
    ScanStatus.SCANNING,
    ScanStatus.ANALYZING,
    ScanStatus.NEEDS_INPUT,
    ScanStatus.READY,
    ScanStatus.FAILED,
}


class ScanService:
    def __init__(
        self,
        repository: ScanRepository,
        *,
        app_mode: str,
        now: Callable[[], datetime],
        storage: StoragePort | None = None,
        queue: ScanQueuePort | None = None,
    ) -> None:
        self._repository = repository
        self._app_mode = app_mode
        self._now = now
        self._storage = storage
        self._queue = queue

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

    async def add_frame(
        self,
        *,
        scan_session_id: str,
        user_id: int,
        content: bytes,
        content_type: str,
        purpose: ImagePurpose,
    ) -> ScanFrameRead:
        record = await self._repository.get_for_user(
            scan_session_id, user_id, for_update=True
        )
        if record is None:
            raise APIError(404, "scan_session_not_found", "没有找到本次扫描")
        if ScanStatus(record.status) not in UNFINISHED_SCAN_STATUSES:
            raise APIError(409, "invalid_scan_transition", "当前扫描状态不能上传图片")
        assessment = assess_image(content)
        if not assessment.accepted:
            status_code = 413 if assessment.reason == "image_too_large" else 422
            raise APIError(
                status_code,
                assessment.reason or "invalid_image",
                "图片不符合扫描要求",
            )
        expected_format = {"image/jpeg": "JPEG", "image/png": "PNG"}.get(content_type)
        if expected_format is None or assessment.image_format != expected_format:
            raise APIError(422, "unsupported_image_type", "仅支持 JPEG 或 PNG 图片")
        duplicate = next(
            (
                image
                for image in record.images
                if image.sha256 == assessment.sha256
                or hamming_distance(
                    image.perceptual_hash, assessment.perceptual_hash
                )
                <= 4
            ),
            None,
        )
        if duplicate is not None:
            return ScanFrameRead(
                id=duplicate.id,
                purpose=ImagePurpose(duplicate.purpose),
                analysis_status=duplicate.analysis_status,
                duplicate=True,
            )
        if len(record.images) >= 4:
            raise APIError(409, "frame_limit_reached", "一次扫描最多上传四张关键帧")
        if self._storage is None:  # pragma: no cover - API always injects storage
            raise RuntimeError("scan image storage is not configured")
        suffix = ".jpg" if content_type == "image/jpeg" else ".png"
        stored = await self._storage.save_scan_image(
            user_id=user_id,
            session_id=scan_session_id,
            content=content,
            suffix=suffix,
            content_type=content_type,
        )
        try:
            image = await self._repository.add_image(
                record,
                ScanImageCreateData(
                    purpose=purpose,
                    storage_path=str(stored.path),
                    content_type=stored.content_type,
                    sha256=assessment.sha256,
                    perceptual_hash=assessment.perceptual_hash,
                    width=assessment.width,
                    height=assessment.height,
                    brightness=assessment.brightness,
                    sharpness=assessment.sharpness,
                ),
            )
            await self._repository.commit()
        except BaseException:
            await self._storage.delete(stored)
            raise
        if self._queue is None:  # pragma: no cover - API always injects queue
            raise RuntimeError("scan analysis queue is not configured")
        try:
            await self._queue.enqueue(image.id)
        except Exception as exc:
            await self._repository.delete_image(image)
            await self._repository.commit()
            await self._storage.delete(stored)
            raise APIError(
                503, "queue_unavailable", "识别队列暂时不可用", True
            ) from exc
        return ScanFrameRead(
            id=image.id,
            purpose=ImagePurpose(image.purpose),
            analysis_status=image.analysis_status,
            duplicate=False,
        )

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
                    purpose=ImagePurpose(image.purpose),
                    analysis_status=image.analysis_status,
                )
                for image in record.images
            ],
        )
