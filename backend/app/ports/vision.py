"""Visual food identity provider contract used by the analysis graph."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.scans import AnyDetectedField
from app.ports.storage import StoredImage


@dataclass(frozen=True, slots=True)
class VisionResult:
    fields: dict[str, AnyDetectedField]


@runtime_checkable
class VisionPort(Protocol):
    async def identify(
        self, images: Sequence[StoredImage], ocr_text: str
    ) -> VisionResult: ...

