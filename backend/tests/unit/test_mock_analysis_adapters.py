from datetime import date
from pathlib import Path

import pytest

from app.adapters.mock_ocr import MockOcrAdapter
from app.adapters.mock_vision import MockVisionAdapter
from app.domain.scans import ImagePurpose
from app.ports.storage import StoredImage


def _stored_image(image_id: int = 1) -> StoredImage:
    return StoredImage(
        path=Path(f"D:/mock/{image_id}.jpg"),
        content_type="image/jpeg",
        source_image_id=image_id,
    )


@pytest.mark.asyncio
async def test_packaged_success_mock_returns_required_ocr_fields() -> None:
    result = await MockOcrAdapter("packaged_success", 1).extract(
        _stored_image(), ImagePurpose.GENERAL
    )

    assert result.text == "鲜牛奶 生产日期 2026-08-18 保质期7天 冷藏"
    assert result.fields["production_date"].value == date(2026, 8, 18)
    assert result.fields["shelf_life_days"].value == 7
    assert result.fields["storage_type"].value == "chilled"


@pytest.mark.asyncio
async def test_identity_followup_mock_returns_name_from_vision() -> None:
    first_ocr = await MockOcrAdapter("needs_identity", 1).extract(
        _stored_image(), ImagePurpose.DATE
    )
    identity = await MockVisionAdapter("needs_identity", 2).identify(
        [_stored_image(2)], first_ocr.text
    )

    assert "food_name" not in first_ocr.fields
    assert identity.fields["food_name"].value == "伊利鲜牛奶"
    assert identity.fields["brand"].value == "伊利"
    assert identity.fields["category"].value == "dairy"


@pytest.mark.asyncio
async def test_fresh_produce_mock_returns_visual_identity_without_dates() -> None:
    ocr = await MockOcrAdapter("fresh_produce", 1).extract(
        _stored_image(), ImagePurpose.GENERAL
    )
    vision = await MockVisionAdapter("fresh_produce", 1).identify(
        [_stored_image()], ocr.text
    )

    assert ocr.fields == {}
    assert vision.fields["food_name"].value == "草莓"
    assert vision.fields["category"].value == "fruit"

