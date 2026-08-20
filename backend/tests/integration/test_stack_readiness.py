import pytest

from app.core.config import Settings
from app.core.errors import APIError
from app.main import probe_readiness


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
