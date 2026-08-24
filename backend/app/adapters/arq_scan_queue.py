"""Lazily connected ARQ queue adapter used by the API process."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class ArqScanQueue:
    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(self._settings)
        return self._pool

    async def enqueue(self, scan_image_id: int) -> None:
        pool = await self._get_pool()
        await pool.enqueue_job(
            "analyze_scan_frame",
            scan_image_id,
            _job_id=f"scan-image-{scan_image_id}",
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None

