import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_live_returns_service_identity(client):
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "xianzhi-api"}


@pytest.mark.asyncio
async def test_ready_reports_injected_dependencies(client):
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "mysql": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_ready_returns_retryable_envelope_when_a_dependency_is_unavailable() -> None:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:1/xianzhi",
        redis_url="redis://127.0.0.1:6379/0",
    )
    app = create_app(settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            response = await test_client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "dependencies_unavailable",
            "message": "服务依赖暂时不可用",
            "retryable": True,
        }
    }
