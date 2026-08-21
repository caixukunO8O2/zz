"""Use cases for creating, reading, and cancelling scan sessions."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

from app.core.errors import APIError
from app.domain.foods import StorageType
from app.domain.scans import (
    DetectedField,
    FieldSource,
    ImagePurpose,
    ScanFields,
    ScanStatus,
    conflicts_from_json,
    scan_fields_from_json,
    scan_fields_to_json,
)
from app.models.entities import User
from app.models.scan_entities import ScanSession
from app.ports.scan_queue import ScanQueuePort
from app.ports.storage import StoragePort
from app.repositories.scans import ScanImageCreateData, ScanRepository
from app.schemas.scans import (
    ScanFinalizeRequest,
    ScanFrameRead,
    ScanImageRead,
    ScanSessionCreate,
    ScanSessionRead,
)
from app.services.food_service import FoodService
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
        timezone=None,
    ) -> None:
        self._repository = repository
        self._app_mode = app_mode
        self._now = now
        self._storage = storage
        self._queue = queue
        self._timezone = timezone

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
    def _user_field(value, evidence: str):
        return DetectedField(
            value=value,
            confidence=1,
            source_image_id=None,
            source_kind=FieldSource.USER,
            evidence_text=evidence,
        )

    @classmethod
    def _apply_user_fields(
        cls, fields: ScanFields, payload: ScanFinalizeRequest
    ) -> ScanFields:
        supplied = payload.model_fields_set
        if "food_name" in supplied and payload.food_name is not None:
            fields = replace(
                fields, food_name=cls._user_field(payload.food_name, "用户确认名称")
            )
        if "brand" in supplied:
            fields = replace(
                fields,
                brand=(
                    cls._user_field(payload.brand, "用户确认品牌")
                    if payload.brand is not None
                    else None
                ),
            )
        if "category" in supplied:
            fields = replace(
                fields,
                category=(
                    cls._user_field(payload.category, "用户确认分类")
                    if payload.category is not None
                    else None
                ),
            )
        if "production_date" in supplied:
            fields = replace(
                fields,
                production_date=(
                    cls._user_field(payload.production_date, "用户确认生产日期")
                    if payload.production_date is not None
                    else None
                ),
            )
        if "declared_expiry_date" in supplied:
            fields = replace(
                fields,
                declared_expiry_date=(
                    cls._user_field(payload.declared_expiry_date, "用户确认有效日期")
                    if payload.declared_expiry_date is not None
                    else None
                ),
            )
        if "shelf_life_days" in supplied:
            fields = replace(
                fields,
                shelf_life_days=(
                    cls._user_field(payload.shelf_life_days, "用户确认保质期")
                    if payload.shelf_life_days is not None
                    else None
                ),
            )
        if "storage_type" in supplied and payload.storage_type is not None:
            fields = replace(
                fields,
                storage_type=cls._user_field(payload.storage_type, "用户确认保存方式"),
            )
        return fields

    async def finalize(
        self,
        *,
        scan_session_id: str,
        user_id: int,
        payload: ScanFinalizeRequest,
        foods: FoodService,
    ):
        record = await self._repository.get_for_user(
            scan_session_id, user_id, for_update=True
        )
        if record is None:
            raise APIError(404, "scan_session_not_found", "没有找到本次扫描")
        if ScanStatus(record.status) not in {
            ScanStatus.READY,
            ScanStatus.NEEDS_INPUT,
        }:
            raise APIError(409, "invalid_scan_transition", "当前扫描状态不能确认")
        fields = scan_fields_from_json(record.detected_fields)
        conflicts = conflicts_from_json(record.conflicts)
        if conflicts:
            if payload.date_conflict_choice is None:
                raise APIError(
                    422,
                    "date_conflict_requires_choice",
                    "请选择正确的包装日期",
                )
            selected = (
                conflicts[0].existing
                if payload.date_conflict_choice == "existing"
                else conflicts[0].candidate
            )
            fields = replace(
                fields,
                declared_expiry_date=self._user_field(
                    cast(DetectedField, selected).value, "用户选择日期证据"
                ),
            )
        fields = self._apply_user_fields(fields, payload)
        if fields.food_name is None or fields.storage_type is None:
            raise APIError(422, "missing_required_scan_fields", "请确认食品名称和保存方式")
        if self._timezone is None:  # pragma: no cover - API always injects timezone
            raise RuntimeError("scan timezone is not configured")
        added_on = (
            record.expires_at - timedelta(hours=24)
        ).astimezone(self._timezone).date()
        thumbnail = None
        if record.images:
            if self._storage is None:  # pragma: no cover - API injects storage
                raise RuntimeError("scan image storage is not configured")
            best_image = min(
                record.images,
                key=lambda image: (
                    {"identity": 0, "general": 1}.get(image.purpose, 2),
                    image.id,
                ),
            )
            thumbnail = await self._storage.create_thumbnail(
                user_id=user_id,
                session_id=record.id,
                source_path=Path(best_image.storage_path),
            )
        try:
            food = await foods.create_from_scan(
                user_id,
                scan_session_id=record.id,
                payload=payload,
                food_name=fields.food_name.value,
                brand=fields.brand.value if fields.brand is not None else None,
                category=(
                    fields.category.value if fields.category is not None else None
                ),
                production_date=(
                    fields.production_date.value
                    if fields.production_date is not None
                    else None
                ),
                declared_expiry_date=(
                    fields.declared_expiry_date.value
                    if fields.declared_expiry_date is not None
                    else None
                ),
                shelf_life_days=(
                    fields.shelf_life_days.value
                    if fields.shelf_life_days is not None
                    else None
                ),
                storage_type=StorageType(fields.storage_type.value),
                added_on=added_on,
                thumbnail_path=str(thumbnail.path) if thumbnail is not None else None,
                confidence_summary=scan_fields_to_json(fields),
            )
            await self._repository.set_status(record, ScanStatus.FINALIZED)
        except BaseException:
            if thumbnail is not None and self._storage is not None:
                await self._storage.delete(thumbnail)
            raise
        return food

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
