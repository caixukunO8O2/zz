"""Local D-drive-backed storage adapter for scan images."""

from asyncio import to_thread
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.ports.storage import StoredImage


class LocalScanStorage:
    def __init__(self, upload_dir: Path) -> None:
        self._root = upload_dir.resolve()

    @staticmethod
    def _validate_component(value: str) -> None:
        if not value or Path(value).name != value or "/" in value or "\\" in value:
            raise ValueError("resolved path is outside upload directory")

    async def save_scan_image(
        self,
        *,
        user_id: int,
        session_id: str,
        content: bytes,
        suffix: str,
        content_type: str,
    ) -> StoredImage:
        self._validate_component(str(user_id))
        self._validate_component(session_id)
        if suffix not in {".jpg", ".png"}:
            raise ValueError("unsupported image suffix")
        target = (
            self._root
            / "scans"
            / str(user_id)
            / session_id
            / f"{uuid4()}{suffix}"
        ).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError("resolved path is outside upload directory")
        await to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await to_thread(target.write_bytes, content)
        return StoredImage(path=target, content_type=content_type)

    async def delete(self, stored: StoredImage) -> None:
        if stored.path.exists() and stored.path.resolve().is_relative_to(self._root):
            await to_thread(stored.path.unlink)

    @staticmethod
    def _render_thumbnail(source: Path, target: Path) -> None:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((480, 480), Image.Resampling.LANCZOS)
            image.save(target, format="JPEG", quality=80, optimize=True)

    async def create_thumbnail(
        self, *, user_id: int, session_id: str, source_path: Path
    ) -> StoredImage:
        self._validate_component(str(user_id))
        self._validate_component(session_id)
        source = source_path.resolve()
        if not source.is_relative_to(self._root) or not source.is_file():
            raise ValueError("thumbnail source is outside upload directory")
        target = (
            self._root / "thumbnails" / str(user_id) / f"{session_id}.jpg"
        ).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError("resolved path is outside upload directory")
        await to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await to_thread(self._render_thumbnail, source, target)
        return StoredImage(path=target, content_type="image/jpeg")
