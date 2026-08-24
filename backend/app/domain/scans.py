"""Scan-session domain types shared by analysis and persistence layers."""

from dataclasses import dataclass, fields, replace
from datetime import date
from enum import StrEnum
from typing import Generic, TypeVar, cast

from app.domain.foods import StorageType

T = TypeVar("T", str, int, date, StorageType)


class ScanStatus(StrEnum):
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    NEEDS_INPUT = "needs_input"
    READY = "ready"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ImagePurpose(StrEnum):
    GENERAL = "general"
    IDENTITY = "identity"
    DATE = "date"
    STORAGE = "storage"


class FieldSource(StrEnum):
    OCR = "ocr"
    VISION = "vision"
    USER = "user"


@dataclass(frozen=True, slots=True)
class DetectedField(Generic[T]):
    value: T
    confidence: float
    source_image_id: int | None
    source_kind: FieldSource
    evidence_text: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class ScanFields:
    food_name: DetectedField[str] | None = None
    brand: DetectedField[str] | None = None
    category: DetectedField[str] | None = None
    production_date: DetectedField[date] | None = None
    declared_expiry_date: DetectedField[date] | None = None
    shelf_life_days: DetectedField[int] | None = None
    storage_type: DetectedField[StorageType] | None = None

    def detected_names(self) -> set[str]:
        return {
            item.name for item in fields(self) if getattr(self, item.name) is not None
        }


AnyDetectedField = (
    DetectedField[str]
    | DetectedField[int]
    | DetectedField[date]
    | DetectedField[StorageType]
)


@dataclass(frozen=True, slots=True)
class FieldCandidate:
    field_name: str
    field: AnyDetectedField

    def __post_init__(self) -> None:
        if self.field_name not in {item.name for item in fields(ScanFields)}:
            raise ValueError(f"unknown scan field: {self.field_name}")


@dataclass(frozen=True, slots=True)
class FieldConflict:
    field_name: str
    existing: AnyDetectedField
    candidate: AnyDetectedField


@dataclass(frozen=True, slots=True)
class MergeResult:
    fields: ScanFields
    conflicts: tuple[FieldConflict, ...]


_SOURCE_PRIORITY = {
    FieldSource.VISION: 1,
    FieldSource.OCR: 2,
    FieldSource.USER: 3,
}


def _replace_field(scan_fields: ScanFields, candidate: FieldCandidate) -> ScanFields:
    field = candidate.field
    if candidate.field_name == "food_name":
        return replace(scan_fields, food_name=cast(DetectedField[str], field))
    if candidate.field_name == "brand":
        return replace(scan_fields, brand=cast(DetectedField[str], field))
    if candidate.field_name == "category":
        return replace(scan_fields, category=cast(DetectedField[str], field))
    if candidate.field_name == "production_date":
        return replace(
            scan_fields, production_date=cast(DetectedField[date], field)
        )
    if candidate.field_name == "declared_expiry_date":
        return replace(
            scan_fields,
            declared_expiry_date=cast(DetectedField[date], field),
        )
    if candidate.field_name == "shelf_life_days":
        return replace(
            scan_fields, shelf_life_days=cast(DetectedField[int], field)
        )
    return replace(
        scan_fields, storage_type=cast(DetectedField[StorageType], field)
    )


def merge_fields(
    existing: ScanFields, candidates: list[FieldCandidate]
) -> MergeResult:
    merged = existing
    conflicts: list[FieldConflict] = []
    for item in candidates:
        current = getattr(merged, item.field_name)
        if current is None:
            merged = _replace_field(merged, item)
            continue
        if current.value == item.field.value:
            if (
                _SOURCE_PRIORITY[item.field.source_kind], item.field.confidence
            ) > (_SOURCE_PRIORITY[current.source_kind], current.confidence):
                merged = _replace_field(merged, item)
            continue
        if item.field_name == "declared_expiry_date":
            conflicts.append(
                FieldConflict(item.field_name, current, item.field)
            )
            continue
        if (
            _SOURCE_PRIORITY[item.field.source_kind], item.field.confidence
        ) > (_SOURCE_PRIORITY[current.source_kind], current.confidence):
            merged = _replace_field(merged, item)
    return MergeResult(merged, tuple(conflicts))


def detected_field_to_json(field: AnyDetectedField) -> dict[str, object]:
    value = field.value
    if isinstance(value, date):
        serialized_value: object = value.isoformat()
    elif isinstance(value, StorageType):
        serialized_value = value.value
    else:
        serialized_value = value
    return {
        "value": serialized_value,
        "confidence": field.confidence,
        "source_image_id": field.source_image_id,
        "source_kind": field.source_kind.value,
        "evidence_text": field.evidence_text,
    }


def _detected_field_from_json(
    field_name: str, payload: dict[str, object]
) -> AnyDetectedField:
    raw_value = payload["value"]
    confidence = float(str(payload["confidence"]))
    source_image_id = (
        int(str(payload["source_image_id"]))
        if payload.get("source_image_id") is not None
        else None
    )
    source_kind = FieldSource(str(payload["source_kind"]))
    evidence_text = str(payload["evidence_text"])
    if field_name in {"production_date", "declared_expiry_date"}:
        return DetectedField(
            value=date.fromisoformat(str(raw_value)),
            confidence=confidence,
            source_image_id=source_image_id,
            source_kind=source_kind,
            evidence_text=evidence_text,
        )
    if field_name == "shelf_life_days":
        return DetectedField(
            value=int(str(raw_value)),
            confidence=confidence,
            source_image_id=source_image_id,
            source_kind=source_kind,
            evidence_text=evidence_text,
        )
    if field_name == "storage_type":
        return DetectedField(
            value=StorageType(str(raw_value)),
            confidence=confidence,
            source_image_id=source_image_id,
            source_kind=source_kind,
            evidence_text=evidence_text,
        )
    return DetectedField(
        value=str(raw_value),
        confidence=confidence,
        source_image_id=source_image_id,
        source_kind=source_kind,
        evidence_text=evidence_text,
    )


def scan_fields_to_json(scan_fields: ScanFields) -> dict[str, object]:
    return {
        item.name: detected_field_to_json(value)
        for item in fields(scan_fields)
        if (value := getattr(scan_fields, item.name)) is not None
    }


def scan_fields_from_json(payload: dict[str, object]) -> ScanFields:
    candidates = [
        FieldCandidate(
            field_name,
            _detected_field_from_json(field_name, cast(dict[str, object], value)),
        )
        for field_name, value in payload.items()
    ]
    return merge_fields(ScanFields(), candidates).fields


def conflicts_to_json(conflicts: tuple[FieldConflict, ...]) -> list[dict[str, object]]:
    return [
        {
            "field_name": conflict.field_name,
            "existing": detected_field_to_json(conflict.existing),
            "candidate": detected_field_to_json(conflict.candidate),
        }
        for conflict in conflicts
    ]


def conflicts_from_json(payload: list[dict[str, object]]) -> tuple[FieldConflict, ...]:
    return tuple(
        FieldConflict(
            field_name=str(item["field_name"]),
            existing=_detected_field_from_json(
                str(item["field_name"]), cast(dict[str, object], item["existing"])
            ),
            candidate=_detected_field_from_json(
                str(item["field_name"]), cast(dict[str, object], item["candidate"])
            ),
        )
        for item in payload
    )


INITIAL_MISSING_FIELDS = ["food_name", "date", "storage_type"]
INITIAL_GUIDANCE = "请先对准商品正面或完整食材"
