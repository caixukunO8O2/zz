"""Scoped idempotency record operations."""

import json
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.idempotency import IdempotencyRecord

MAX_RESPONSE_JSON_BYTES = 16_384


class IdempotencyConflict(ValueError):
    """Raised when a scoped key is reused for different request content."""


class IdempotencyResponseTooLarge(ValueError):
    """Raised when replay data exceeds the bounded response payload size."""


@dataclass(frozen=True, slots=True)
class IdempotencyBeginResult:
    """The persisted record and whether this caller acquired execution ownership."""

    record: IdempotencyRecord
    acquired: bool


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
    ) -> IdempotencyBeginResult:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                mysql_insert(IdempotencyRecord)
                .values(
                    user_id=user_id,
                    route=route,
                    idempotency_key=key,
                    request_hash=request_hash,
                    status="in_progress",
                )
                .prefix_with("IGNORE")
            ),
        )
        acquired = result.rowcount == 1
        record = await self._session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.route == route,
                IdempotencyRecord.idempotency_key == key,
            )
            .with_for_update()
        )
        if record is None:  # pragma: no cover - guarded by the insert/unique key
            raise RuntimeError("idempotency insert did not produce a readable row")
        self._verify_hash(record, request_hash)
        return IdempotencyBeginResult(record=record, acquired=acquired)

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
        serialized = json.dumps(response_json, ensure_ascii=False, separators=(",", ":"))
        storage_size = await self._session.scalar(
            select(func.json_storage_size(serialized))
        )
        if storage_size is None or storage_size > MAX_RESPONSE_JSON_BYTES:
            raise IdempotencyResponseTooLarge(
                "idempotency response JSON storage exceeds 16384 bytes"
            )
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
