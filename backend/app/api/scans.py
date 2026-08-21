"""Authenticated scan-session routes."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse

from app.adapters.local_storage import LocalScanStorage
from app.api.deps import CurrentUser, SessionDependency
from app.core.errors import APIError
from app.domain.scans import ImagePurpose
from app.repositories.scans import ScanRepository
from app.schemas.scans import ScanFrameRead, ScanSessionCreate, ScanSessionRead
from app.services.image_quality import MAX_IMAGE_BYTES
from app.services.scan_service import ScanService

router = APIRouter(prefix="/scan-sessions", tags=["scan-sessions"])


def _service(request: Request, session: SessionDependency) -> ScanService:
    return ScanService(
        ScanRepository(session),
        app_mode=request.app.state.settings.app_mode,
        now=request.app.state.now_provider,
        storage=LocalScanStorage(request.app.state.settings.upload_dir),
    )


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
    if idempotency_key is None or not idempotency_key.strip():
        raise APIError(400, "idempotency_key_required", "缺少幂等键")
    if len(idempotency_key.strip()) > 255:
        raise APIError(400, "invalid_idempotency_key", "幂等键不正确")
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
