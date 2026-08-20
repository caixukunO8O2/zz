from collections.abc import Callable

from fastapi import APIRouter, FastAPI, Request

from app.core.config import Settings, get_settings

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
) -> FastAPI:
    app = FastAPI(title="鲜知 API")
    app.state.settings = settings or get_settings()
    app.state.readiness_probe = readiness_probe or default_readiness_probe
    app.include_router(health_router, prefix="/api/v1")
    return app


app = create_app()
