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
_LABEL_PATTERN = r"(?:^|\n)\s*{label}\s*[:：]\s*([^\r\n]+)"


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


def _label_value(text: str, label: str) -> str | None:
    match = re.search(_LABEL_PATTERN.format(label=re.escape(label)), text)
    return _clean(match.group(1)) if match else None


def _shelf_life_days(value: object) -> int | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(年|个?月|天|日)", cleaned)
    if match is None:
        return _days(cleaned)
    amount = float(match.group(1))
    unit = match.group(2)
    multiplier = 365 if unit == "年" else 30 if "月" in unit else 1
    days = round(amount * multiplier)
    return days if 1 <= days <= 36_600 else None


def _storage_type(value: object) -> StorageType | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    normalized = cleaned.lower()
    for keywords, storage in (
        (("冷冻", "冻结", "frozen"), StorageType.FROZEN),
        (("冷藏", "chilled"), StorageType.CHILLED),
        (
            ("常温", "室温", "阴凉", "干燥", "通风", "避光", "防潮", "room"),
            StorageType.ROOM,
        ),
    ):
        if any(keyword in normalized for keyword in keywords):
            return storage
    return None


def _compact_packaging_date(text: str) -> date | None:
    production_text = _label_value(text, "生产日期")
    if production_text is None or "见包装" not in production_text:
        return None
    for match in re.finditer(r"(?<!\d)(20\d{6})(?!\d)", text):
        value = match.group(1)
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        except ValueError:
            continue
    return None


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
                "ocr_options": {"task": "text_recognition"},
                "max_tokens": 2_048,
            },
        )
        content = first_content(payload)
        result = content.get("ocr_result")
        values = result.get("kv_result") if isinstance(result, dict) else None
        if not isinstance(values, dict):
            values = {}
        processed_text = result.get("processed_text") if isinstance(result, dict) else None
        raw_text = _clean(content.get("text")) or _clean(processed_text)
        if raw_text is None:
            raise BailianProviderError("Bailian OCR response was invalid")
        image_id = image.source_image_id
        fields: dict[str, AnyDetectedField] = {}

        for key, field_name in (("商品名称", "food_name"), ("品牌", "brand")):
            raw_value = _label_value(raw_text, key)
            if key == "商品名称" and raw_value is None:
                raw_value = _label_value(raw_text, "产品名称")
            if value := _clean(values.get(key)) or raw_value:
                fields[field_name] = _field(value[:128], image_id, f"{key}: {value}")
        if value := _clean(values.get("食材分类")):
            category = _CATEGORY_ALIASES.get(value, value.lower())
            if category in _CATEGORIES:
                fields["category"] = _field(category, image_id, f"食材分类: {value}")
        for key, field_name in (
            ("生产日期", "production_date"),
            ("过期日期", "declared_expiry_date"),
        ):
            parsed_date = _date(values.get(key) or _label_value(raw_text, key))
            if key == "生产日期" and parsed_date is None:
                parsed_date = _compact_packaging_date(raw_text)
            if parsed_date is not None:
                fields[field_name] = _field(
                    parsed_date, image_id, f"{key}: {values.get(key)}"
                )
        shelf_text = values.get("保质期天数") or _label_value(raw_text, "保质期")
        shelf_days = _shelf_life_days(shelf_text)
        if shelf_days is not None:
            fields["shelf_life_days"] = _field(
                shelf_days, image_id, f"保质期: {shelf_text}"
            )
        if value := _clean(values.get("储存条件")) or _label_value(raw_text, "储存条件"):
            storage = _storage_type(value)
            if storage is not None:
                fields["storage_type"] = _field(storage, image_id, f"储存条件: {value}")
        return OcrResult(text=raw_text, fields=fields)
