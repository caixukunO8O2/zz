"""User persistence operations."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_openid(self, openid: str) -> User:
        existing = await self._session.scalar(select(User).where(User.openid == openid))
        if existing is not None:
            return existing

        try:
            async with self._session.begin_nested():
                created = User(openid=openid)
                self._session.add(created)
                await self._session.flush()
            return created
        except IntegrityError:
            concurrent = await self._session.scalar(select(User).where(User.openid == openid))
            if concurrent is None:
                raise
            return concurrent
