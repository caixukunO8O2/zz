"""Authenticated scan-session routes."""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse

from app.adapters.local_storage import LocalScanStorage
from app.api.deps import CurrentUser, SessionDependency
from app.core.errors import APIError
from app.domain.scans import ImagePurpose
from app.repositories.foods import FoodRepository
from app.repositories.idempotency import IdempotencyConflict, IdempotencyRepository
from app.repositories.rules import RuleRepository
from app.repositories.scans import ScanRepository
from app.schemas.scans import (
    ScanFinalizeRequest,
    ScanFinalizeResponse,
    ScanFrameRead,
    ScanSessionCreate,
    ScanSessionRead,
)
from app.services.food_service import FoodService
from app.services.image_quality import MAX_IMAGE_BYTES
from app.services.scan_service import ScanService

router = APIRouter(prefix="/scan-sessions", tags=["scan-sessions"])


def _service(request: Request, session: SessionDependency) -> ScanService:
    return ScanService(
        ScanRepository(session),
        app_mode=request.app.state.settings.app_mode,
        now=request.app.state.now_provider,
        storage=LocalScanStorage(request.app.state.settings.upload_dir),
        queue=request.app.state.scan_queue,
        timezone=request.app.state.timezone,
    )


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


@router.post("", status_code=201, response_model=ScanSessionRead)
async def create_scan_session(
    payload: ScanSessionCreate,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanSessionRead:
    service = _service(request, session)
    return service.present(await service.create(current_user, payload))


@router.get("/{scan_session_id}", response_model=ScanSessionRead)
async def get_scan_session(
    scan_session_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanSessionRead:
    service = _service(request, session)
    return service.present(await service.get_for_user(scan_session_id, current_user.id))


@router.post("/{scan_session_id}/cancel", response_model=ScanSessionRead)
async def cancel_scan_session(
    scan_session_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> ScanSessionRead:
    service = _service(request, session)
    return service.present(await service.cancel(scan_session_id, current_user.id))


@router.post(
    "/{scan_session_id}/finalize",
    response_model=ScanFinalizeResponse,
)
async def finalize_scan_session(
    scan_session_id: str,
    payload: ScanFinalizeRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    key = _require_idempotency_key(idempotency_key)
    route = f"/scan-sessions/{scan_session_id}/finalize"
    request_hash = _request_hash(payload.model_dump(mode="json", exclude_unset=True))
    idempotency = IdempotencyRepository(session)
    try:
        begun = await idempotency.begin(
            current_user.id, route, key, request_hash
        )
    except IdempotencyConflict as exc:
        raise APIError(409, "idempotency_conflict", "幂等键已用于其他请求") from exc
    if not begun.acquired:
        if begun.record.status == "completed" and begun.record.response_json is not None:
            return JSONResponse(status_code=200, content=begun.record.response_json)
        raise APIError(409, "idempotency_in_progress", "请求正在处理中", True)
    today = (
        request.app.state.now_provider()
        .astimezone(request.app.state.timezone)
        .date()
    )
    food_service = FoodService(
        FoodRepository(session), RuleRepository(session), today=today
    )
    food = await _service(request, session).finalize(
        scan_session_id=scan_session_id,
        user_id=current_user.id,
        payload=payload,
        foods=food_service,
    )
    body = ScanFinalizeResponse(
        food=food_service.present(food)
    ).model_dump(mode="json")
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


@router.post("/{scan_session_id}/frames", response_model=ScanFrameRead)
async def upload_scan_frame(
    scan_session_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    image: Annotated[UploadFile, File()],
    purpose: Annotated[ImagePurpose, Form()],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    _require_idempotency_key(idempotency_key)
    content = await image.read(MAX_IMAGE_BYTES + 1)
    result = await _service(request, session).add_frame(
        scan_session_id=scan_session_id,
        user_id=current_user.id,
        content=content,
        content_type=image.content_type or "",
        purpose=purpose,
    )
    return JSONResponse(
        status_code=200 if result.duplicate else 202,
        content=result.model_dump(mode="json"),
    )
