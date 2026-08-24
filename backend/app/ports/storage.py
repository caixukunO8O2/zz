"""Storage boundary for original scan images."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredImage:
    path: Path
    content_type: str
    source_image_id: int | None = None


class StoragePort(Protocol):
    async def save_scan_image(
        self,
        *,
        user_id: int,
        session_id: str,
        content: bytes,
        suffix: str,
        content_type: str,
    ) -> StoredImage: ...

    async def delete(self, stored: StoredImage) -> None: ...

    async def create_thumbnail(
        self, *, user_id: int, session_id: str, source_path: Path
    ) -> StoredImage: ...
