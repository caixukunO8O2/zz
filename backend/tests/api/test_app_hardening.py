import asyncio

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.main import create_app

GENERATED_STYLE_JWT_SECRET = "aB3_dE5-fG7_hJ9-kL2_mN4-pQ6_rS8-tU0_vW1-xYz"


@pytest.mark.parametrize(
    "jwt_secret",
    [
        "",
        "change-me-for-production",
        "x" * 31,
        "x" * 32,
        "12345678" * 4,
        "0123456789" * 4,
        "0123456789" * 5,
        f" {GENERATED_STYLE_JWT_SECRET} ",
    ],
)
def test_real_mode_rejects_blank_placeholder_short_or_patterned_jwt_secret(
    jwt_secret: str,
) -> None:
    settings = Settings(app_mode="real", jwt_secret=jwt_secret)

    with pytest.raises(ValueError, match="JWT signing secret"):
        create_app(settings)


def test_real_mode_accepts_generated_urlsafe_jwt_secret() -> None:
    settings = Settings(app_mode="real", jwt_secret=GENERATED_STYLE_JWT_SECRET)

    app = create_app(settings)

    assert app.state.settings.jwt_secret == GENERATED_STYLE_JWT_SECRET


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


@pytest.mark.asyncio
async def test_method_not_allowed_preserves_allow_header() -> None:
    app = create_app(Settings(app_mode="mock"))
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post("/api/v1/health/live")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


@pytest.mark.asyncio
async def test_http_auth_error_preserves_www_authenticate_header() -> None:
    app = create_app(Settings(app_mode="mock"))
    router = APIRouter()

    @router.get("/auth-challenge")
    async def auth_challenge() -> None:
        raise StarletteHTTPException(
            401,
            headers={"WWW-Authenticate": 'Bearer realm="provider"'},
        )

    app.include_router(router)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/auth-challenge")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="provider"'
