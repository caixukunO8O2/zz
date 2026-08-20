from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://test:test@mysql/test",
        redis_url="redis://redis:6379/0",
    )

    def readiness_probe() -> dict[str, str]:
        return {"mysql": "ok", "redis": "ok"}

    transport = ASGITransport(app=create_app(settings, readiness_probe=readiness_probe))
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
