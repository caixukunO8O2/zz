"""OCR provider contract used by the scan analysis graph."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.scans import AnyDetectedField, ImagePurpose
from app.ports.storage import StoredImage


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    fields: dict[str, AnyDetectedField]


@runtime_checkable
class OcrPort(Protocol):
    async def extract(
        self, image: StoredImage, purpose: ImagePurpose
    ) -> OcrResult: ...

