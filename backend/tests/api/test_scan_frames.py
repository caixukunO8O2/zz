import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.local_storage import LocalScanStorage
from app.core.config import Settings
from app.main import create_app
from app.models.entities import FoodRecord, User
from app.models.idempotency import IdempotencyRecord
from app.models.scan_entities import ScanImage, ScanSession

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi_test",
)
TEST_JWT_SECRET = (
    "aB3_dE5-fG7_hJ9-kL2_mN4-pQ6_rS8-tU0_vW1-xYz"
    "A7_cD9-eF2_gH4-jK6_mN8-pQ"
)
FIXED_NOW = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


class _RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list[int] = []

    async def enqueue(self, scan_image_id: int) -> None:
        self.enqueued.append(scan_image_id)

    async def close(self) -> None:
        return None


class _FailingQueue(_RecordingQueue):
    async def enqueue(self, scan_image_id: int) -> None:
        raise ConnectionError("redis unavailable")


def _jpeg_bytes(*, dark: bool = False, marker: int = 0) -> bytes:
    image = Image.new("RGB", (640, 640), (5, 5, 5) if dark else (245, 245, 245))
    if not dark:
        draw = ImageDraw.Draw(image)
        for offset in range(marker, 640, 40):
            draw.rectangle(
                (offset, 0, min(offset + 19, 639), 639), fill=(20, 20, 20)
            )
        draw.text((160, 280), f"EXP 2026-08-{20 + marker % 8:02d}", fill=(220, 30, 30))
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


async def _clean_test_database(session: AsyncSession) -> None:
    database_name = await session.scalar(text("SELECT DATABASE()"))
    if database_name != "xianzhi_test":
        raise RuntimeError(
            f"refusing scan-frame cleanup on database {database_name!r}"
        )
    for model in (ScanImage, ScanSession, IdempotencyRecord, FoodRecord, User):
        await session.execute(delete(model))


@pytest_asyncio.fixture
async def api_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _clean_test_database(session)
        await session.commit()
    yield factory
    async with factory() as session:
        await _clean_test_database(session)
        await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    api_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
        upload_dir=tmp_path / "uploads",
    )
    app = create_app(
        settings,
        session_factory=api_session_factory,
        now_provider=lambda: FIXED_NOW,
        scan_queue=_RecordingQueue(),
    )
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as value:
            yield value


async def _auth_headers(client: AsyncClient, code: str = "frame-owner") -> dict[str, str]:
    response = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_scan(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/scan-sessions",
        json={"mock_scenario": "packaged_success"},
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["id"])


@pytest.mark.asyncio
async def test_accepted_frame_is_stored_under_configured_upload_root(
    client: AsyncClient,
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _auth_headers(client)
    scan_id = await _create_scan(client, headers)

    response = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": ("label.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"purpose": "date"},
        headers={**headers, "Idempotency-Key": "frame-1"},
    )

    assert response.status_code == 202
    assert response.json()["analysis_status"] == "queued"
    assert "storage_path" not in response.json()
    async with api_session_factory() as session:
        stored = await session.scalar(
            select(ScanImage).where(ScanImage.id == response.json()["id"])
        )
        assert stored is not None
        stored_path = Path(stored.storage_path).resolve()
        assert stored_path.is_file()
        assert "uploads" in stored_path.parts


@pytest.mark.asyncio
async def test_duplicate_frame_reuses_existing_image_without_consuming_limit(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client, "duplicate-owner")
    scan_id = await _create_scan(client, headers)
    content = _jpeg_bytes()

    first = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": ("first.jpg", content, "image/jpeg")},
        data={"purpose": "general"},
        headers={**headers, "Idempotency-Key": "duplicate-1"},
    )
    duplicate = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": ("same.jpg", content, "image/jpeg")},
        data={"purpose": "date"},
        headers={**headers, "Idempotency-Key": "duplicate-2"},
    )

    assert first.status_code == 202
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["duplicate"] is True


@pytest.mark.asyncio
async def test_dark_frame_is_rejected_with_stable_error(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "dark-owner")
    scan_id = await _create_scan(client, headers)

    response = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": ("dark.jpg", _jpeg_bytes(dark=True), "image/jpeg")},
        data={"purpose": "general"},
        headers={**headers, "Idempotency-Key": "dark-frame"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "image_too_dark"


@pytest.mark.asyncio
async def test_fifth_unique_frame_is_rejected(
    client: AsyncClient,
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await _auth_headers(client, "limit-owner")
    scan_id = await _create_scan(client, headers)
    async with api_session_factory() as session:
        for index in range(4):
            session.add(
                ScanImage(
                    scan_session_id=scan_id,
                    purpose="general",
                    storage_path=f"D:/fixture/{index}.jpg",
                    content_type="image/jpeg",
                    sha256=f"{index:064x}",
                    perceptual_hash=f"{index * 0x1111111111111111:016x}",
                    width=640,
                    height=640,
                    brightness=120,
                    sharpness=30,
                    analysis_status="queued",
                )
            )
        await session.commit()

    response = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": ("fifth.jpg", _jpeg_bytes(marker=7), "image/jpeg")},
        data={"purpose": "date"},
        headers={**headers, "Idempotency-Key": "frame-5"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "frame_limit_reached"


@pytest.mark.asyncio
async def test_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalScanStorage(tmp_path / "uploads")

    with pytest.raises(ValueError, match="outside upload directory"):
        await storage.save_scan_image(
            user_id=1,
            session_id="../../escape",
            content=_jpeg_bytes(),
            suffix=".jpg",
            content_type="image/jpeg",
        )


@pytest.mark.asyncio
async def test_queue_failure_removes_database_row_and_stored_file(
    api_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    upload_dir = tmp_path / "failed-queue-uploads"
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
        upload_dir=upload_dir,
    )
    app = create_app(
        settings,
        session_factory=api_session_factory,
        now_provider=lambda: FIXED_NOW,
        scan_queue=_FailingQueue(),
    )
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as failing_client:
            headers = await _auth_headers(failing_client, "queue-failure-owner")
            scan_id = await _create_scan(failing_client, headers)
            response = await failing_client.post(
                f"/api/v1/scan-sessions/{scan_id}/frames",
                files={"image": ("label.jpg", _jpeg_bytes(), "image/jpeg")},
                data={"purpose": "general"},
                headers={**headers, "Idempotency-Key": "queue-failure"},
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "queue_unavailable"
    async with api_session_factory() as session:
        assert list(await session.scalars(select(ScanImage))) == []
    assert list(upload_dir.rglob("*.*")) == []
