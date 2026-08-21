"""Typed state and injected dependencies for scan analysis."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from app.domain.date_rules import DateCalculation
from app.domain.foods import StorageType
from app.domain.scans import (
    FieldCandidate,
    FieldConflict,
    ImagePurpose,
    ScanFields,
)
from app.ports.ocr import OcrPort
from app.ports.storage import StoredImage
from app.ports.vision import VisionPort


class AnalysisState(TypedDict, total=False):
    image: StoredImage
    images: list[StoredImage]
    purpose: ImagePurpose
    fields: ScanFields
    pending_candidates: list[FieldCandidate]
    conflicts: tuple[FieldConflict, ...]
    ocr_text: str
    visual_required: bool
    added_on: date
    date_calculation: DateCalculation | None
    status: str
    missing_fields: list[str]
    next_guidance: str


RuleDaysLookup = Callable[[str, StorageType], Awaitable[int | None]]
PersistAnalysis = Callable[[AnalysisState], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AnalysisDependencies:
    ocr: OcrPort
    vision: VisionPort
    rule_days: RuleDaysLookup
    persist: PersistAnalysis | None = None

