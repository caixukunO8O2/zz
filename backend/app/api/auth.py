"""WeChat login route."""

from fastapi import APIRouter, Request

from app.api.deps import SessionDependency
from app.repositories.users import UserRepository
from app.schemas.auth import TokenResponse, WechatLoginRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/wechat/login", response_model=TokenResponse)
async def wechat_login(
    payload: WechatLoginRequest,
    request: Request,
    session: SessionDependency,
) -> TokenResponse:
    service = AuthService(UserRepository(session), request.app.state.wechat_auth)
    token = await service.login(payload.code, request.app.state.settings.jwt_secret)
    return TokenResponse(access_token=token)
