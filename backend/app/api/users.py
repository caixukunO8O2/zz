"""Current-user profile routes."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDependency
from app.models.entities import User
from app.repositories.users import UserRepository
from app.schemas.users import ProfileUpdate, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


def _present_user(user: User) -> UserRead:
    return UserRead(id=user.id, nickname=user.nickname, avatar_url=user.avatar_url)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return _present_user(current_user)


@router.patch("/me/profile", response_model=UserRead)
async def update_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser,
    session: SessionDependency,
) -> UserRead:
    service = AuthService(UserRepository(session), None)
    updated = await service.update_profile(current_user, payload)
    return _present_user(updated)
