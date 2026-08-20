"""WeChat login and local profile use cases."""

from app.core.errors import APIError
from app.core.security import create_access_token
from app.models.entities import User
from app.ports.wechat_auth import WechatAuthPort, WechatAuthUnavailable
from app.repositories.users import PROFILE_UNSET, ProfileFieldUnset, UserRepository
from app.schemas.users import ProfileUpdate


class AuthService:
    def __init__(
        self, users: UserRepository, wechat_auth: WechatAuthPort | None
    ) -> None:
        self._users = users
        self._wechat_auth = wechat_auth

    async def login(self, code: str, jwt_secret: str) -> str:
        if self._wechat_auth is None:  # pragma: no cover - route always injects auth
            raise RuntimeError("WeChat auth is required for login")
        try:
            identity = self._wechat_auth.exchange_code(code)
        except WechatAuthUnavailable as exc:
            raise APIError(
                503,
                "wechat_auth_unavailable",
                "微信登录当前不可用",
            ) from exc
        user = await self._users.get_or_create_by_openid(identity.openid)
        return create_access_token(user.id, jwt_secret)

    async def update_profile(self, user: User, payload: ProfileUpdate) -> User:
        nickname: str | None | ProfileFieldUnset = PROFILE_UNSET
        avatar_url: str | None | ProfileFieldUnset = PROFILE_UNSET
        if "nickname" in payload.model_fields_set:
            nickname = payload.nickname
        if "avatar_url" in payload.model_fields_set:
            avatar_url = str(payload.avatar_url) if payload.avatar_url is not None else None
        return await self._users.update_profile(
            user,
            nickname=nickname,
            avatar_url=avatar_url,
        )
