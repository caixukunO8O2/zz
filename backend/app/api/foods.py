"""Authenticated food CRUD routes."""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, SessionDependency
from app.core.errors import APIError
from app.domain.foods import FreshnessBucket
from app.repositories.foods import FoodRepository
from app.repositories.idempotency import IdempotencyConflict, IdempotencyRepository
from app.repositories.rules import RuleRepository
from app.schemas.foods import FoodList, FoodManualCreate, FoodPatch, FoodRead
from app.services.food_service import FoodService

router = APIRouter(prefix="/foods", tags=["foods"])
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _request_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _require_idempotency_key(key: str | None) -> str:
    if key is None or not key.strip():
        raise APIError(400, "idempotency_key_required", "缺少幂等键")
    normalized = key.strip()
    if len(normalized) > 255:
        raise APIError(400, "invalid_idempotency_key", "幂等键不正确")
    return normalized


def _service(request: Request, session: SessionDependency) -> FoodService:
    today = (
        request.app.state.now_provider()
        .astimezone(request.app.state.timezone)
        .date()
    )
    return FoodService(
        FoodRepository(session),
        RuleRepository(session),
        today=today,
    )


@router.get("", response_model=FoodList)
async def list_foods(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    bucket: Annotated[FreshnessBucket | None, Query()] = None,
) -> FoodList:
    service = _service(request, session)
    records = await service.list_for_user(current_user.id, bucket)
    return FoodList(items=[service.present(record) for record in records])


@router.post("/manual", status_code=201)
async def create_manual_food(
    payload: FoodManualCreate,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    idempotency_key: IdempotencyKey = None,
) -> Response:
    key = _require_idempotency_key(idempotency_key)
    route = "/foods/manual"
    request_hash = _request_hash(payload.model_dump(mode="json", exclude_unset=True))
    idempotency = IdempotencyRepository(session)
    try:
        begun = await idempotency.begin(current_user.id, route, key, request_hash)
    except IdempotencyConflict as exc:
        raise APIError(409, "idempotency_conflict", "幂等键已用于其他请求") from exc
    if not begun.acquired:
        record = begun.record
        if record.status == "completed" and record.response_json is not None:
            return JSONResponse(
                status_code=record.response_status or 201,
                content=record.response_json,
            )
        raise APIError(409, "idempotency_in_progress", "请求正在处理中", True)
    service = _service(request, session)
    food = await service.create_manual(current_user.id, payload)
    body = service.present(food).model_dump(mode="json")
    await idempotency.complete(
        current_user.id,
        route,
        key,
        request_hash,
        response_status=201,
        response_resource_id=str(food.id),
        response_json=body,
    )
    return JSONResponse(status_code=201, content=body)


@router.get("/{food_id}", response_model=FoodRead)
async def get_food(
    food_id: int,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> FoodRead:
    service = _service(request, session)
    return service.present(await service.get_for_user(food_id, current_user.id))


@router.patch("/{food_id}", response_model=FoodRead)
async def update_food(
    food_id: int,
    payload: FoodPatch,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> FoodRead:
    service = _service(request, session)
    return service.present(await service.update(food_id, current_user.id, payload))


@router.delete("/{food_id}", status_code=204)
async def delete_food(
    food_id: int,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    idempotency_key: IdempotencyKey = None,
) -> Response:
    key = _require_idempotency_key(idempotency_key)
    route = f"/foods/{food_id}"
    request_hash = _request_hash({})
    idempotency = IdempotencyRepository(session)
    try:
        begun = await idempotency.begin(current_user.id, route, key, request_hash)
    except IdempotencyConflict as exc:
        raise APIError(409, "idempotency_conflict", "幂等键已用于其他请求") from exc
    if not begun.acquired:
        if begun.record.status == "completed":
            return Response(status_code=begun.record.response_status or 204)
        raise APIError(409, "idempotency_in_progress", "请求正在处理中", True)
    service = _service(request, session)
    await service.soft_delete(food_id, current_user.id)
    await idempotency.complete(
        current_user.id,
        route,
        key,
        request_hash,
        response_status=204,
        response_resource_id=str(food_id),
        response_json={},
    )
    return Response(status_code=204)
