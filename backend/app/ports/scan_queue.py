"""Queue boundary between frame upload and asynchronous scan analysis."""

from typing import Protocol


class ScanQueuePort(Protocol):
    async def enqueue(self, scan_image_id: int) -> None: ...

    async def close(self) -> None: ...

