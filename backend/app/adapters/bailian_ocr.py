"""Qwen OCR adapter for labelled food-package information."""

import re
from datetime import date

from app.adapters.bailian_client import BailianClientPort, BailianProviderError, first_content
from app.domain.foods import StorageType
from app.domain.scans import AnyDetectedField, DetectedField, FieldSource, ImagePurpose
from app.ports.ocr import OcrResult
from app.ports.storage import StoredImage

_CATEGORIES = {"fruit", "vegetable", "meat", "dairy", "cooked"}
_CATEGORY_ALIASES = {
    "水果": "fruit",
    "蔬菜": "vegetable",
    "肉类": "meat",
    "乳制品": "dairy",
    "熟食": "cooked",
}
_STORAGE_ALIASES = {
    "常温": StorageType.ROOM,
    "室温": StorageType.ROOM,
    "room": StorageType.ROOM,
    "冷藏": StorageType.CHILLED,
    "chilled": StorageType.CHILLED,
    "冷冻": StorageType.FROZEN,
    "frozen": StorageType.FROZEN,
}


def _clean(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned or cleaned.lower() in {"null", "none", "未识别", "?"}:
        return None
    return cleaned


def _date(value: object) -> date | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", cleaned)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _days(value: object) -> int | None:
    cleaned = _clean(value)
    match = re.search(r"\d+", cleaned) if cleaned else None
    if match is None:
        return None
    days = int(match.group())
    return days if 1 <= days <= 36_600 else None


def _field(value, image_id: int | None, evidence: str) -> AnyDetectedField:
    return DetectedField(
        value=value,
        confidence=0.9,
        source_image_id=image_id,
        source_kind=FieldSource.OCR,
        evidence_text=evidence[:512],
    )


class BailianOcrAdapter:
    def __init__(self, client: BailianClientPort, model: str) -> None:
        self._client = client
        self._model = model

    async def extract(self, image: StoredImage, purpose: ImagePurpose) -> OcrResult:
        del purpose
        payload = await self._client.generate(
            model=self._model,
            images=[image],
            parameters={
                "ocr_options": {
                    "task": "key_information_extraction",
                    "task_config": {
                        "result_schema": {
                            "商品名称": "包装上完整的商品或食材名称，没有则为null",
                            "品牌": "包装上的品牌名称，没有则为null",
                            "食材分类": "仅返回fruit、vegetable、meat、dairy、cooked之一",
                            "生产日期": "YYYY-MM-DD，没有明确标注则为null",
                            "过期日期": (
                                "明确标注的到期、失效或有效期截止日期，"
                                "YYYY-MM-DD，没有则为null"
                            ),
                            "保质期天数": "换算为天数的整数，没有则为null",
                            "储存条件": "仅返回常温、冷藏、冷冻之一，没有则为null",
                        }
                    },
                }
            },
        )
        content = first_content(payload)
        result = content.get("ocr_result")
        values = result.get("kv_result") if isinstance(result, dict) else None
        if not isinstance(values, dict):
            raise BailianProviderError("Bailian OCR response was invalid")
        raw_text = _clean(content.get("text")) or " ".join(
            str(value) for value in values.values() if _clean(value)
        )
        image_id = image.source_image_id
        fields: dict[str, AnyDetectedField] = {}

        for key, field_name in (("商品名称", "food_name"), ("品牌", "brand")):
            if value := _clean(values.get(key)):
                fields[field_name] = _field(value[:128], image_id, f"{key}: {value}")
        if value := _clean(values.get("食材分类")):
            category = _CATEGORY_ALIASES.get(value, value.lower())
            if category in _CATEGORIES:
                fields["category"] = _field(category, image_id, f"食材分类: {value}")
        for key, field_name in (
            ("生产日期", "production_date"),
            ("过期日期", "declared_expiry_date"),
        ):
            parsed_date = _date(values.get(key))
            if parsed_date is not None:
                fields[field_name] = _field(
                    parsed_date, image_id, f"{key}: {values.get(key)}"
                )
        shelf_days = _days(values.get("保质期天数"))
        if shelf_days is not None:
            fields["shelf_life_days"] = _field(
                shelf_days, image_id, f"保质期天数: {values.get('保质期天数')}"
            )
        if value := _clean(values.get("储存条件")):
            storage = _STORAGE_ALIASES.get(value.lower()) or _STORAGE_ALIASES.get(value)
            if storage is not None:
                fields["storage_type"] = _field(storage, image_id, f"储存条件: {value}")
        return OcrResult(text=raw_text, fields=fields)
