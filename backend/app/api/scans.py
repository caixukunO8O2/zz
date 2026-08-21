"""Authenticated scan-session routes."""

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, SessionDependency
from app.repositories.scans import ScanRepository
from app.schemas.scans import ScanSessionCreate, ScanSessionRead
from app.services.scan_service import ScanService

router = APIRouter(prefix="/scan-sessions", tags=["scan-sessions"])


def _service(request: Request, session: SessionDependency) -> ScanService:
    return ScanService(
        ScanRepository(session),
        app_mode=request.app.state.settings.app_mode,
        now=request.app.state.now_provider,
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

