"""Scoped idempotency record operations."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.idempotency import IdempotencyRecord

MAX_RESPONSE_JSON_BYTES = 16_384


class IdempotencyConflict(ValueError):
    """Raised when a scoped key is reused for different request content."""


class IdempotencyResponseTooLarge(ValueError):
    """Raised when replay data exceeds the bounded response payload size."""


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, user_id: int, route: str, key: str) -> IdempotencyRecord | None:
        return await self._session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.route == route,
                IdempotencyRecord.idempotency_key == key,
            )
        )

    @staticmethod
    def _verify_hash(record: IdempotencyRecord, request_hash: str) -> None:
        if record.request_hash != request_hash:
            raise IdempotencyConflict("idempotency key was reused with a different request hash")

    async def begin(
        self, user_id: int, route: str, key: str, request_hash: str
    ) -> IdempotencyRecord:
        existing = await self._get(user_id, route, key)
        if existing is not None:
            self._verify_hash(existing, request_hash)
            return existing
        record = IdempotencyRecord(
            user_id=user_id,
            route=route,
            idempotency_key=key,
            request_hash=request_hash,
            status="in_progress",
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def complete(
        self,
        user_id: int,
        route: str,
        key: str,
        request_hash: str,
        *,
        response_status: int,
        response_resource_id: str | None,
        response_json: dict[str, object],
    ) -> IdempotencyRecord:
        encoded = json.dumps(response_json, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > MAX_RESPONSE_JSON_BYTES:
            raise IdempotencyResponseTooLarge("idempotency response JSON exceeds 16384 bytes")
        record = await self._get(user_id, route, key)
        if record is None:
            raise LookupError("idempotency record has not been started")
        self._verify_hash(record, request_hash)
        record.status = "completed"
        record.response_status = response_status
        record.response_resource_id = response_resource_id
        record.response_json = response_json
        record.updated_at = utc_now()
        await self._session.flush()
        return record

    async def get_replay(
        self, user_id: int, route: str, key: str, request_hash: str
    ) -> IdempotencyRecord | None:
        record = await self._get(user_id, route, key)
        if record is None:
            return None
        self._verify_hash(record, request_hash)
        return record if record.status == "completed" else None
