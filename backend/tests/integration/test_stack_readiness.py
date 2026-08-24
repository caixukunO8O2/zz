import asyncio

import pytest

from app.core.config import Settings
from app.core.errors import APIError
from app.main import probe_readiness


class FakeConnection:
    def __init__(self) -> None:
        self.error: Exception | None = None

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        if self.error is not None:
            raise self.error


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.disposed = False

    def connect(self) -> FakeConnection:
        return self.connection

    async def dispose(self) -> None:
        self.disposed = True


class FakeRedis:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        self.closed = False

    async def ping(self) -> bool:
        if self.outcome == "error":
            raise ConnectionError("redis unavailable")
        if self.outcome == "timeout":
            await asyncio.Event().wait()
        return True

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_real_readiness_reports_mysql_and_redis() -> None:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi",
        redis_url="redis://127.0.0.1:6379/0",
    )

    result = await probe_readiness(settings)

    assert result == {"status": "ready", "mysql": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_real_readiness_maps_dependency_failure_without_leaking_details() -> None:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:1/xianzhi",
        redis_url="redis://127.0.0.1:6379/0",
    )

    with pytest.raises(APIError) as raised:
        await probe_readiness(settings)

    assert raised.value.status_code == 503
    assert raised.value.code == "dependencies_unavailable"
    assert raised.value.message == "服务依赖暂时不可用"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_real_readiness_requires_redis_ping() -> None:
    settings = Settings(
        app_mode="mock",
        database_url="mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi",
        redis_url="redis://127.0.0.1:1/0",
    )

    with pytest.raises(APIError) as raised:
        await probe_readiness(settings)

    assert raised.value.status_code == 503
    assert raised.value.code == "dependencies_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_outcome", ["success", "error", "timeout"])
async def test_readiness_always_closes_created_resources(
    redis_outcome: str,
) -> None:
    settings = Settings(app_mode="mock")
    engine = FakeEngine()
    redis = FakeRedis(redis_outcome)

    if redis_outcome == "success":
        assert await probe_readiness(
            settings,
            engine_factory=lambda url: engine,
            redis_factory=lambda url: redis,
            timeout_seconds=0.01,
        ) == {"status": "ready", "mysql": "ok", "redis": "ok"}
    else:
        with pytest.raises(APIError) as raised:
            await probe_readiness(
                settings,
                engine_factory=lambda url: engine,
                redis_factory=lambda url: redis,
                timeout_seconds=0.01,
            )
        assert raised.value.code == "dependencies_unavailable"

    assert engine.disposed is True
    assert redis.closed is True
