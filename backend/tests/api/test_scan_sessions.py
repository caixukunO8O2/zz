import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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


async def _clean_existing_tables(session: AsyncSession) -> None:
    database_name = await session.scalar(text("SELECT DATABASE()"))
    if database_name != "xianzhi_test":
        raise RuntimeError(
            f"refusing scan API-test cleanup on database {database_name!r}"
        )
    for model in (ScanImage, ScanSession, IdempotencyRecord, FoodRecord, User):
        await session.execute(delete(model))


@pytest_asyncio.fixture
async def api_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _clean_existing_tables(session)
        await session.commit()
    yield factory
    async with factory() as session:
        await _clean_existing_tables(session)
        await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    api_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = create_app(
        settings,
        session_factory=api_session_factory,
        now_provider=lambda: FIXED_NOW,
    )
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as value:
            yield value


async def _auth_headers(client: AsyncClient, code: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_scan_session_returns_empty_progress(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "scan-owner")

    response = await client.post(
        "/api/v1/scan-sessions",
        json={"mock_scenario": "packaged_success"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json() | {"id": "ignored", "expires_at": "ignored"} == {
        "id": "ignored",
        "expires_at": "ignored",
        "status": "scanning",
        "detected_fields": {},
        "conflicts": [],
        "missing_fields": ["food_name", "date", "storage_type"],
        "next_guidance": "请先对准商品正面或完整食材",
        "images": [],
    }


@pytest.mark.asyncio
async def test_scan_session_is_user_scoped(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, "scan-scope-owner")
    stranger_headers = await _auth_headers(client, "scan-scope-stranger")
    created = await client.post(
        "/api/v1/scan-sessions", json={}, headers=owner_headers
    )
    assert created.status_code == 201

    response = await client.get(
        f"/api/v1/scan-sessions/{created.json()['id']}",
        headers=stranger_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "scan_session_not_found"


@pytest.mark.asyncio
async def test_cancel_marks_unfinished_session_cancelled(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "scan-cancel-owner")
    created = await client.post("/api/v1/scan-sessions", json={}, headers=headers)
    assert created.status_code == 201

    first = await client.post(
        f"/api/v1/scan-sessions/{created.json()['id']}/cancel", headers=headers
    )
    replay = await client.post(
        f"/api/v1/scan-sessions/{created.json()['id']}/cancel", headers=headers
    )

    assert first.status_code == replay.status_code == 200
    assert first.json()["status"] == replay.json()["status"] == "cancelled"
