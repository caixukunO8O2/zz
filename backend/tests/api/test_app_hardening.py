import asyncio

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.core.config import Settings
from app.main import create_app

TEST_JWT_SECRET = "real-signing-material-with-at-least-thirty-two-bytes"


@pytest.mark.parametrize(
    "jwt_secret",
    ["", "change-me-for-production", "x" * 31, "x" * 32],
)
def test_real_mode_rejects_blank_placeholder_or_short_jwt_secret(
    jwt_secret: str,
) -> None:
    settings = Settings(app_mode="real", jwt_secret=jwt_secret)

    with pytest.raises(ValueError, match="JWT signing secret"):
        create_app(settings)


def test_invalid_configured_timezone_fails_during_app_creation() -> None:
    settings = Settings(app_mode="mock", app_timezone="Mars/Olympus")

    with pytest.raises(ValueError, match="application timezone"):
        create_app(settings)


@pytest.mark.asyncio
async def test_each_app_created_engine_is_disposed_by_lifespan() -> None:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://test:test@mysql/test",
    )
    apps = [create_app(settings), create_app(settings)]
    disposed = [asyncio.Event(), asyncio.Event()]
    for app, signal in zip(apps, disposed, strict=True):
        event.listen(
            app.state.database_engine.sync_engine,
            "engine_disposed",
            lambda engine, signal=signal: signal.set(),
        )

    for app in apps:
        async with app.router.lifespan_context(app):
            pass

    assert all(signal.is_set() for signal in disposed)


@pytest.mark.asyncio
async def test_unhandled_and_http_errors_use_stable_json_envelopes() -> None:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://test:test@mysql/test",
    )
    app = create_app(settings)
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("sensitive implementation detail")

    app.include_router(router)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            internal = await client.get("/boom")
            missing = await client.get("/does-not-exist")

    assert internal.status_code == 500
    assert internal.json() == {
        "error": {
            "code": "internal_error",
            "message": "服务器内部错误",
            "retryable": False,
        }
    }
    assert "sensitive" not in internal.text
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "not_found",
            "message": "请求的资源不存在",
            "retryable": False,
        }
    }
