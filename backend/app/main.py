from collections.abc import Callable

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.mock_wechat_auth import MockWechatAuthAdapter
from app.api.auth import router as auth_router
from app.api.foods import router as foods_router
from app.api.users import router as users_router
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db import create_session_factory

ReadinessProbe = Callable[[], dict[str, str]]

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
) -> FastAPI:
    app = FastAPI(title="鲜知 API")
    app.state.settings = settings or get_settings()
    app.state.readiness_probe = readiness_probe or default_readiness_probe
    app.state.session_factory = session_factory or create_session_factory(
        app.state.settings.database_url
    )
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

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(foods_router, prefix="/api/v1")
    return app


app = create_app()
