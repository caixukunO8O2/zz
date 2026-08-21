"""ARQ worker lifecycle and runtime settings."""

from typing import Any

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.db import create_session_factory
from app.workers.scan_tasks import analyze_scan_frame


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["session_factory"] = create_session_factory(settings.database_url)


async def shutdown(ctx: dict[str, Any]) -> None:
    factory = ctx.get("session_factory")
    if factory is not None:
        engine = factory.kw.get("bind")
        if isinstance(engine, AsyncEngine):
            await engine.dispose()


class WorkerSettings:
    functions = [analyze_scan_frame]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    max_tries = 3
    job_timeout = 35
    health_check_interval = 30

