"""Application database engine and transactional session boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()
_engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    connect_args={"init_command": "SET time_zone = '+00:00'"},
)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Create an application-owned session factory for an injected database URL."""
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield one session, committing on success and rolling back on error."""
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
