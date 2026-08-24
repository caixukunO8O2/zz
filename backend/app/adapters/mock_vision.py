"""Deterministic visual identity adapter for V1 demonstration scenarios."""

from collections.abc import Sequence

from app.adapters.mock_ocr import MOCK_SCENARIOS
from app.domain.scans import DetectedField, FieldSource
from app.ports.storage import StoredImage
from app.ports.vision import VisionResult


def _vision_field(
    value: str, image_id: int | None, evidence: str, confidence: float
) -> DetectedField[str]:
    return DetectedField(
        value=value,
        confidence=confidence,
        source_image_id=image_id,
        source_kind=FieldSource.VISION,
        evidence_text=evidence,
    )


class MockVisionAdapter:
    def __init__(self, scenario: str, frame_index: int) -> None:
        if scenario not in MOCK_SCENARIOS:
            raise ValueError(f"unknown mock scan scenario: {scenario}")
        self._scenario = scenario
        self._frame_index = frame_index

    async def identify(
        self, images: Sequence[StoredImage], ocr_text: str
    ) -> VisionResult:
        image_id = images[-1].source_image_id if images else None
        if self._scenario == "fresh_produce":
            return VisionResult(
                fields={
                    "food_name": _vision_field(
                        "草莓", image_id, "红色草莓果实", 0.96
                    ),
                    "category": _vision_field(
                        "fruit", image_id, "新鲜水果", 0.95
                    ),
                }
            )
        if self._scenario == "needs_identity" and self._frame_index == 1:
            return VisionResult(fields={})
        return VisionResult(
            fields={
                "food_name": _vision_field(
                    "伊利鲜牛奶", image_id, "伊利鲜牛奶正面包装", 0.94
                ),
                "brand": _vision_field("伊利", image_id, "伊利商标", 0.96),
                "category": _vision_field(
                    "dairy", image_id, "牛奶包装", 0.93
                ),
            }
        )

