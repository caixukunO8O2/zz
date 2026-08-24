"""ARQ task that serializes and persists scan-frame analysis."""

from asyncio import timeout
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from arq import Retry
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.bailian_client import BailianProviderError
from app.adapters.factory import create_analysis_adapters
from app.agents.graph import AnalysisDependencies, build_analysis_graph
from app.agents.state import AnalysisState
from app.core.config import Settings
from app.domain.foods import StorageType
from app.domain.scans import (
    ImagePurpose,
    ScanFields,
    conflicts_from_json,
    conflicts_to_json,
    scan_fields_from_json,
    scan_fields_to_json,
)
from app.ports.storage import StoredImage
from app.repositories.rules import RuleRepository
from app.repositories.scans import ScanRepository

AnalysisRunner = Callable[[AnalysisState], Awaitable[AnalysisState]]


def _knowledge_days(rule, storage: StorageType) -> int | None:
    if rule is None:
        return None
    if storage is StorageType.ROOM:
        return rule.room_days
    if storage is StorageType.CHILLED:
        return rule.chilled_days
    return rule.frozen_days


async def _mark_failed(
    factory: async_sessionmaker[AsyncSession], scan_image_id: int, code: str
) -> None:
    async with factory() as session:
        async with session.begin():
            repository = ScanRepository(session)
            image = await repository.get_image(scan_image_id)
            if image is None:
                return
            record = await repository.lock_for_analysis(image.scan_session_id)
            if record is None:
                return
            current = next(
                (candidate for candidate in record.images if candidate.id == image.id),
                image,
            )
            await repository.set_image_status(current, "failed", code)
            record.status = "failed"
            record.next_guidance = "识别服务暂时没有响应，请重新拍摄当前画面"


async def analyze_scan_frame(ctx: dict[str, Any], scan_image_id: int) -> None:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    settings = cast(Settings, ctx["settings"])
    try:
        async with factory() as session:
            async with session.begin():
                repository = ScanRepository(session)
                image = await repository.get_image(scan_image_id)
                if image is None:
                    return
                record = await repository.lock_for_analysis(image.scan_session_id)
                if record is None:
                    return
                current = next(
                    (
                        candidate
                        for candidate in record.images
                        if candidate.id == scan_image_id
                    ),
                    None,
                )
                if current is None or current.analysis_status == "completed":
                    return
                await repository.set_image_status(current, "analyzing")
                record.status = "analyzing"
                ordered_images = sorted(record.images, key=lambda item: item.id)
                frame_index = next(
                    index
                    for index, item in enumerate(ordered_images, start=1)
                    if item.id == current.id
                )
                adapters = create_analysis_adapters(
                    analysis_provider=settings.analysis_provider,
                    mock_scenario=record.mock_scenario,
                    frame_index=frame_index,
                    dashscope_api_key=settings.dashscope_api_key,
                    bailian_base_url=settings.bailian_base_url,
                    bailian_ocr_model=settings.bailian_ocr_model,
                    bailian_vision_model=settings.bailian_vision_model,
                )
                rules = RuleRepository(session)

                async def rule_days(
                    food_name: str, storage: StorageType
                ) -> int | None:
                    return _knowledge_days(
                        await rules.find_by_name(food_name), storage
                    )

                dependencies = AnalysisDependencies(
                    ocr=adapters.ocr,
                    vision=adapters.vision,
                    rule_days=rule_days,
                )
                stored_images = [
                    StoredImage(
                        path=Path(item.storage_path),
                        content_type=item.content_type,
                        source_image_id=item.id,
                    )
                    for item in ordered_images
                ]
                current_stored = stored_images[frame_index - 1]
                timezone = ZoneInfo(settings.app_timezone)
                added_on = (
                    record.expires_at - timedelta(hours=24)
                ).astimezone(timezone).date()
                state: AnalysisState = {
                    "image": current_stored,
                    "images": stored_images,
                    "purpose": ImagePurpose(current.purpose),
                    "fields": scan_fields_from_json(record.detected_fields),
                    "conflicts": conflicts_from_json(record.conflicts),
                    "added_on": added_on,
                }
                runner = cast(AnalysisRunner | None, ctx.get("analysis_runner"))
                if runner is None:
                    graph = build_analysis_graph(dependencies)

                    async def runner(value: AnalysisState) -> AnalysisState:
                        return cast(AnalysisState, await graph.ainvoke(value))

                async with timeout(30):
                    result = await runner(state)
                result_fields = result.get("fields", ScanFields())
                result_conflicts = result.get("conflicts", ())
                await repository.save_analysis(
                    record,
                    status=result["status"],
                    detected_fields=scan_fields_to_json(result_fields),
                    conflicts=conflicts_to_json(result_conflicts),
                    missing_fields=result["missing_fields"],
                    next_guidance=result["next_guidance"],
                )
                await repository.set_image_status(current, "completed")
    except (TimeoutError, BailianProviderError) as exc:
        attempt = int(ctx.get("job_try", 1))
        if attempt < 3:
            raise Retry(defer=2**attempt) from exc
        code = (
            "analysis_timeout"
            if isinstance(exc, TimeoutError)
            else "analysis_provider_failed"
        )
        await _mark_failed(factory, scan_image_id, code)
