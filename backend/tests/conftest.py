import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.main import create_app
from app.models.entities import FoodRecord, User
from app.models.idempotency import IdempotencyRecord
from app.models.scan_entities import ScanImage, ScanSession
from app.workers.scan_tasks import analyze_scan_frame

SCAN_TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi_test",
)
SCAN_TEST_JWT_SECRET = (
    "aB3_dE5-fG7_hJ9-kL2_mN4-pQ6_rS8-tU0_vW1-xYz"
    "A7_cD9-eF2_gH4-jK6_mN8-pQ"
)
SCAN_FIXED_NOW = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://test:test@mysql/test",
        redis_url="redis://redis:6379/0",
    )

    async def readiness_probe() -> dict[str, str]:
        return {"status": "ready", "mysql": "ok", "redis": "ok"}

    app = create_app(settings, readiness_probe=readiness_probe)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            yield test_client


async def _clean_scan_test_database(session: AsyncSession) -> None:
    database_name = await session.scalar(text("SELECT DATABASE()"))
    if database_name != "xianzhi_test":
        raise RuntimeError(f"refusing scan-flow cleanup on {database_name!r}")
    for model in (ScanImage, ScanSession, IdempotencyRecord, FoodRecord, User):
        await session.execute(delete(model))


@pytest_asyncio.fixture
async def scan_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(SCAN_TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _clean_scan_test_database(session)
        await session.commit()
    yield factory
    async with factory() as session:
        await _clean_scan_test_database(session)
        await session.commit()
    await engine.dispose()


class _ImmediateAnalysisQueue:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._context = {
            "session_factory": session_factory,
            "settings": settings,
        }

    async def enqueue(self, scan_image_id: int) -> None:
        await analyze_scan_frame(self._context, scan_image_id)

    async def close(self) -> None:
        return None


@pytest_asyncio.fixture
async def scan_client(
    scan_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_mode="mock",
        database_url=SCAN_TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=SCAN_TEST_JWT_SECRET,
        upload_dir=tmp_path / "scan-flow-uploads",
    )
    app = create_app(
        settings,
        session_factory=scan_session_factory,
        now_provider=lambda: SCAN_FIXED_NOW,
        scan_queue=_ImmediateAnalysisQueue(scan_session_factory, settings),
    )
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as value:
            yield value


@pytest_asyncio.fixture
async def scan_auth_headers(scan_client: AsyncClient):
    async def authenticate(code: str = "scan-flow-owner") -> dict[str, str]:
        response = await scan_client.post(
            "/api/v1/auth/wechat/login", json={"code": code}
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return authenticate


@pytest_asyncio.fixture
async def scan_image_bytes():
    def build(orientation: str = "vertical") -> bytes:
        image = Image.new("RGB", (640, 640), (242, 242, 242))
        draw = ImageDraw.Draw(image)
        if orientation == "vertical":
            for offset in range(0, 640, 40):
                draw.rectangle((offset, 0, offset + 18, 639), fill=(20, 20, 20))
        else:
            for offset in range(0, 640, 40):
                draw.rectangle((0, offset, 639, offset + 18), fill=(20, 20, 20))
        draw.text((160, 280), "EXP 2026-08-25", fill=(210, 30, 30))
        exif = Image.Exif()
        exif[305] = "scan-test-generator"
        output = BytesIO()
        image.save(output, format="JPEG", quality=90, exif=exif)
        return output.getvalue()

    return build
