"""FastAPI dependencies for database sessions and authenticated users."""

from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIError
from app.core.security import decode_access_token
from app.models.entities import User
from app.repositories.users import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ],
) -> User:
    raw_authorization = request.headers.get("Authorization")
    if raw_authorization is None:
        raise APIError(401, "authentication_required", "请先登录")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise APIError(401, "invalid_token", "登录状态无效")
    try:
        claims = decode_access_token(
            credentials.credentials, request.app.state.settings.jwt_secret
        )
    except jwt.ExpiredSignatureError as exc:
        raise APIError(401, "token_expired", "登录状态已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise APIError(401, "invalid_token", "登录状态无效") from exc
    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None:
        raise APIError(401, "invalid_token", "登录状态无效")
    return user


SessionDependency = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
