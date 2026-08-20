import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://test:test@mysql/test",
        redis_url="redis://redis:6379/0",
    )

    def readiness_probe() -> dict[str, str]:
        return {"mysql": "ok", "redis": "ok"}

    with TestClient(create_app(settings, readiness_probe=readiness_probe)) as test_client:
        yield test_client
