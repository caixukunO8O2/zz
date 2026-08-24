from datetime import date
from pathlib import Path

import pytest

from app.adapters.factory import create_analysis_adapters
from app.agents.graph import AnalysisDependencies, build_analysis_graph
from app.agents.nodes.decide_visual import decide_visual
from app.agents.nodes.run_visual import run_visual
from app.domain.foods import StorageType
from app.domain.scans import DetectedField, FieldSource, ImagePurpose, ScanFields
from app.ports.storage import StoredImage
from app.ports.vision import VisionResult


def _user_storage() -> DetectedField[StorageType]:
    return DetectedField(
        value=StorageType.CHILLED,
        confidence=1,
        source_image_id=None,
        source_kind=FieldSource.USER,
        evidence_text="用户选择冷藏",
    )


async def _rule_days(food_name: str, storage: StorageType) -> int | None:
    if food_name == "草莓" and storage is StorageType.CHILLED:
        return 5
    return None


def _graph(scenario: str, frame_index: int = 1):
    adapters = create_analysis_adapters(
        app_mode="mock",
        mock_scenario=scenario,
        frame_index=frame_index,
    )
    return build_analysis_graph(
        AnalysisDependencies(
            ocr=adapters.ocr,
            vision=adapters.vision,
            rule_days=_rule_days,
        )
    )


def _state(
    *,
    fields: ScanFields | None = None,
    purpose: ImagePurpose = ImagePurpose.GENERAL,
) -> dict[str, object]:
    image = StoredImage(
        path=Path("D:/mock/1.jpg"),
        content_type="image/jpeg",
        source_image_id=1,
    )
    return {
        "image": image,
        "images": [image],
        "purpose": purpose,
        "fields": fields or ScanFields(),
        "conflicts": (),
        "added_on": date(2026, 8, 20),
    }


@pytest.mark.asyncio
async def test_name_missing_requests_identity_frame() -> None:
    result = await _graph("needs_identity").ainvoke(_state())

    assert result["status"] == "needs_input"
    assert result["missing_fields"] == ["food_name"]
    assert result["next_guidance"] == "没有认出是什么，请对准商品正面继续扫描"


@pytest.mark.asyncio
async def test_packaged_food_calculates_production_plus_shelf_life() -> None:
    result = await _graph("packaged_success").ainvoke(_state())

    assert result["fields"].food_name.value == "伊利鲜牛奶"
    assert result["date_calculation"].consume_by == date(2026, 8, 25)
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_fresh_produce_uses_knowledge_date() -> None:
    result = await _graph("fresh_produce").ainvoke(
        _state(fields=ScanFields(storage_type=_user_storage()))
    )

    assert result["fields"].food_name.value == "草莓"
    assert result["date_calculation"].consume_by == date(2026, 8, 25)
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_identity_followup_reuses_existing_date_fields() -> None:
    first = await _graph("needs_identity", 1).ainvoke(_state())
    second = await _graph("needs_identity", 2).ainvoke(
        _state(fields=first["fields"], purpose=ImagePurpose.IDENTITY)
    )

    assert second["fields"].food_name.value == "伊利鲜牛奶"
    assert second["date_calculation"].consume_by == date(2026, 8, 25)
    assert second["status"] == "ready"


def test_packaged_name_does_not_wait_for_optional_visual_category() -> None:
    fields = ScanFields(
        food_name=DetectedField(
            value="鲜牛奶",
            confidence=0.9,
            source_image_id=1,
            source_kind=FieldSource.OCR,
            evidence_text="产品名称：鲜牛奶",
        )
    )

    assert decide_visual({"fields": fields}) == {"visual_required": False}


@pytest.mark.asyncio
async def test_visual_fallback_sends_only_the_current_frame() -> None:
    class RecordingVision:
        def __init__(self) -> None:
            self.received: list[StoredImage] = []

        async def identify(self, images, ocr_text: str) -> VisionResult:
            del ocr_text
            self.received = list(images)
            return VisionResult(fields={})

    vision = RecordingVision()
    previous = StoredImage(Path("D:/mock/previous.jpg"), "image/jpeg", 1)
    current = StoredImage(Path("D:/mock/current.jpg"), "image/jpeg", 2)
    adapters = create_analysis_adapters(
        app_mode="mock", mock_scenario="fresh_produce", frame_index=1
    )

    await run_visual(
        {"image": current, "images": [previous, current], "ocr_text": ""},
        AnalysisDependencies(
            ocr=adapters.ocr,
            vision=vision,
            rule_days=_rule_days,
        ),
    )

    assert vision.received == [current]
