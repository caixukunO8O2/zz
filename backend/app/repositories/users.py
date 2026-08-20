"""User persistence operations."""

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User


class ProfileFieldUnset:
    __slots__ = ()


PROFILE_UNSET = ProfileFieldUnset()


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_openid(self, openid: str) -> User:
        statement = mysql_insert(User).values(openid=openid)
        await self._session.execute(
            statement.on_duplicate_key_update(openid=statement.inserted.openid)
        )
        user = await self._session.scalar(
            select(User).where(User.openid == openid).with_for_update()
        )
        if user is None:  # pragma: no cover - guarded by the insert/upsert statement
            raise RuntimeError("user upsert did not produce a readable row")
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def update_profile(
        self,
        user: User,
        *,
        nickname: str | None | ProfileFieldUnset = PROFILE_UNSET,
        avatar_url: str | None | ProfileFieldUnset = PROFILE_UNSET,
    ) -> User:
        if not isinstance(nickname, ProfileFieldUnset):
            user.nickname = nickname
        if not isinstance(avatar_url, ProfileFieldUnset):
            user.avatar_url = avatar_url
        await self._session.flush()
        return user
