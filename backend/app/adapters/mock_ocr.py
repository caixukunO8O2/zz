"""Deterministic OCR adapter for the three V1 demonstration scenarios."""

from datetime import date

from app.domain.foods import StorageType
from app.domain.scans import DetectedField, FieldSource, ImagePurpose
from app.ports.ocr import OcrResult
from app.ports.storage import StoredImage

MOCK_SCENARIOS = {"packaged_success", "needs_identity", "fresh_produce"}


def _ocr_field(value, image_id: int | None, evidence: str, confidence: float = 0.92):
    return DetectedField(
        value=value,
        confidence=confidence,
        source_image_id=image_id,
        source_kind=FieldSource.OCR,
        evidence_text=evidence,
    )


class MockOcrAdapter:
    def __init__(self, scenario: str, frame_index: int) -> None:
        if scenario not in MOCK_SCENARIOS:
            raise ValueError(f"unknown mock scan scenario: {scenario}")
        self._scenario = scenario
        self._frame_index = frame_index

    async def extract(
        self, image: StoredImage, purpose: ImagePurpose
    ) -> OcrResult:
        image_id = image.source_image_id
        if self._scenario == "fresh_produce":
            return OcrResult(text="", fields={})
        if self._scenario == "needs_identity" and self._frame_index > 1:
            return OcrResult(text="伊利 鲜牛奶", fields={})
        text = "鲜牛奶 生产日期 2026-08-18 保质期7天 冷藏"
        fields = {
            "production_date": _ocr_field(
                date(2026, 8, 18), image_id, "生产日期 2026-08-18"
            ),
            "shelf_life_days": _ocr_field(7, image_id, "保质期7天"),
            "storage_type": _ocr_field(
                StorageType.CHILLED, image_id, "冷藏"
            ),
        }
        if self._scenario == "packaged_success":
            fields.update(
                {
                    "food_name": _ocr_field(
                        "伊利鲜牛奶", image_id, "伊利 鲜牛奶", 0.9
                    ),
                    "brand": _ocr_field("伊利", image_id, "伊利", 0.9),
                    "category": _ocr_field(
                        "dairy", image_id, "鲜牛奶", 0.86
                    ),
                }
            )
        return OcrResult(text=text, fields=fields)

