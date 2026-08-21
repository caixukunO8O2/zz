"""Scan-session domain types shared by analysis and persistence layers."""

from dataclasses import dataclass, fields
from datetime import date
from enum import StrEnum
from typing import Generic, TypeVar

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


INITIAL_MISSING_FIELDS = ["food_name", "date", "storage_type"]
INITIAL_GUIDANCE = "请先对准商品正面或完整食材"

