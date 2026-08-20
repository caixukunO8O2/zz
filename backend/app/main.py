from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.adapters.mock_wechat_auth import MockWechatAuthAdapter
from app.api.auth import router as auth_router
from app.api.foods import router as foods_router
from app.api.users import router as users_router
from app.core.config import Settings, get_settings, validate_runtime_settings
from app.core.errors import APIError
from app.db import create_session_factory

ReadinessProbe = Callable[[], dict[str, str]]
NowProvider = Callable[[], datetime]

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "xianzhi-api"}


@health_router.get("/ready")
def ready(request: Request) -> dict[str, str]:
    dependencies = request.app.state.readiness_probe()
    return {"status": "ready", **dependencies}


def default_readiness_probe() -> dict[str, str]:
    return {"mysql": "ok", "redis": "ok"}


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probe: ReadinessProbe | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    now_provider: NowProvider | None = None,
) -> FastAPI:
    configured_settings = settings or get_settings()
    configured_timezone = validate_runtime_settings(configured_settings)
    database_engine: AsyncEngine | None = None
    if session_factory is None:
        session_factory = create_session_factory(configured_settings.database_url)
        database_engine = cast(AsyncEngine, session_factory.kw["bind"])

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if database_engine is not None:
                await database_engine.dispose()

    app = FastAPI(title="鲜知 API", lifespan=lifespan)
    app.state.settings = configured_settings
    app.state.timezone = configured_timezone
    app.state.now_provider = now_provider or (lambda: datetime.now(UTC))
    app.state.readiness_probe = readiness_probe or default_readiness_probe
    app.state.session_factory = session_factory
    if database_engine is not None:
        app.state.database_engine = database_engine
    app.state.wechat_auth = MockWechatAuthAdapter(app.state.settings.app_mode)

    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.envelope())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=APIError(
                422, "validation_error", "请求参数不正确"
            ).envelope(),
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=APIError(
                503,
                "database_unavailable",
                "数据库暂时不可用",
                True,
            ).envelope(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code == 404:
            error = APIError(404, "not_found", "请求的资源不存在")
        else:
            error = APIError(exc.status_code, "http_error", "请求无法完成")
        return JSONResponse(status_code=error.status_code, content=error.envelope())

    @app.exception_handler(Exception)
    async def handle_internal_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        error = APIError(500, "internal_error", "服务器内部错误")
        return JSONResponse(status_code=500, content=error.envelope())

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(foods_router, prefix="/api/v1")
    return app


app = create_app()
