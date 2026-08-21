"""Qwen multimodal visual adapter for food identity fallback."""

import json
from collections.abc import Sequence

from app.adapters.bailian_client import BailianClientPort, BailianProviderError, first_content
from app.domain.scans import AnyDetectedField, DetectedField, FieldSource
from app.ports.storage import StoredImage
from app.ports.vision import VisionResult

_CATEGORIES = {"fruit", "vegetable", "meat", "dairy", "cooked"}
_PROMPT = """识别图片中的食材或包装商品。OCR文字仅作为辅助证据：{ocr_text}
只输出JSON，不要解释：
{{"food_name": string|null, "brand": string|null,
"category": "fruit"|"vegetable"|"meat"|"dairy"|"cooked"|null,
"confidence": number}}
不要推测生产日期、过期日期、保质期或储存条件。看不清的字段返回null。"""


def _json_object(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise BailianProviderError("Bailian vision response was invalid") from exc
    if not isinstance(value, dict):
        raise BailianProviderError("Bailian vision response was invalid")
    return value


class BailianVisionAdapter:
    def __init__(self, client: BailianClientPort, model: str) -> None:
        self._client = client
        self._model = model

    async def identify(
        self, images: Sequence[StoredImage], ocr_text: str
    ) -> VisionResult:
        payload = await self._client.generate(
            model=self._model,
            images=list(images),
            prompt=_PROMPT.format(ocr_text=ocr_text[:2000]),
            parameters={"result_format": "message"},
        )
        content = first_content(payload)
        raw_text = content.get("text")
        if not isinstance(raw_text, str):
            raise BailianProviderError("Bailian vision response was invalid")
        values = _json_object(raw_text)
        raw_confidence = values.get("confidence", 0.85)
        try:
            confidence = max(0.0, min(1.0, float(str(raw_confidence))))
        except ValueError:
            confidence = 0.85
        image_id = images[-1].source_image_id if images else None
        fields: dict[str, AnyDetectedField] = {}
        for key in ("food_name", "brand"):
            value = values.get(key)
            if isinstance(value, str) and value.strip():
                cleaned = value.strip()[:128]
                fields[key] = DetectedField(
                    value=cleaned,
                    confidence=confidence,
                    source_image_id=image_id,
                    source_kind=FieldSource.VISION,
                    evidence_text=f"视觉识别: {cleaned}",
                )
        category = values.get("category")
        if isinstance(category, str) and category in _CATEGORIES:
            fields["category"] = DetectedField(
                value=category,
                confidence=confidence,
                source_image_id=image_id,
                source_kind=FieldSource.VISION,
                evidence_text=f"视觉分类: {category}",
            )
        return VisionResult(fields=fields)
