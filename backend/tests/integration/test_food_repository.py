import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import CHAR, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.entities import FoodRecord, PreservationRuleModel, User
from app.models.idempotency import IdempotencyRecord
from app.repositories.foods import FoodCreateData, FoodRepository, FoodUpdateData
from app.repositories.idempotency import (
    IdempotencyConflict,
    IdempotencyRepository,
    IdempotencyResponseTooLarge,
)
from app.repositories.rules import RuleRepository
from app.repositories.users import UserRepository

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi_test",
)


def test_scan_linked_id_uses_fixed_width_uuid_storage() -> None:
    column_type = FoodRecord.__table__.c.scan_session_id.type
    assert isinstance(column_type, CHAR)
    assert column_type.length == 36


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        for model in (IdempotencyRecord, FoodRecord, User):
            await session.execute(delete(model))
        await session.commit()
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).get_or_create_by_openid("mock:seeded")


@pytest_asyncio.fixture
async def seeded_user_and_food(
    db_session: AsyncSession, seeded_user: User
) -> tuple[User, FoodRecord]:
    food = await FoodRepository(db_session).create(
        seeded_user.id,
        FoodCreateData(
            food_name="草莓",
            storage_type="chilled",
            recommended_consume_by=date(2026, 8, 25),
            date_basis="knowledge_base_estimate",
        ),
    )
    return seeded_user, food


@pytest.mark.asyncio
async def test_food_repository_is_user_scoped(db_session: AsyncSession) -> None:
    owner = await UserRepository(db_session).get_or_create_by_openid("mock:owner")
    same_owner = await UserRepository(db_session).get_or_create_by_openid("mock:owner")
    stranger = await UserRepository(db_session).get_or_create_by_openid("mock:stranger")
    assert same_owner.id == owner.id
    created = await FoodRepository(db_session).create(
        owner.id,
        FoodCreateData(
            food_name="草莓",
            storage_type="chilled",
            recommended_consume_by=date(2026, 8, 25),
            date_basis="knowledge_base_estimate",
        ),
    )
    repository = FoodRepository(db_session)
    assert await repository.get_for_user(created.id, owner.id) is not None
    assert await repository.get_for_user(created.id, stranger.id) is None
    assert await repository.update(
        created.id, stranger.id, FoodUpdateData(food_name="越权修改")
    ) is None
    assert await repository.soft_delete(created.id, stranger.id) is False


@pytest.mark.asyncio
async def test_food_repository_lists_updates_and_preserves_utc_timestamps(
    db_session: AsyncSession, seeded_user_and_food: tuple[User, FoodRecord]
) -> None:
    user, food = seeded_user_and_food
    repository = FoodRepository(db_session)
    assert [item.id for item in await repository.list_for_user(user.id)] == [food.id]

    updated = await repository.update(
        food.id,
        user.id,
        FoodUpdateData(food_name="洗净草莓", recommended_consume_by=date(2026, 8, 24)),
    )
    assert updated is not None
    assert (updated.food_name, updated.recommended_consume_by) == (
        "洗净草莓",
        date(2026, 8, 24),
    )
    food_id = food.id
    user_id = user.id
    await db_session.flush()
    db_session.expire_all()
    reloaded = await repository.get_for_user(food_id, user_id)
    assert reloaded is not None
    assert reloaded.created_at.tzinfo is not None
    assert reloaded.updated_at.tzinfo is not None
    assert reloaded.created_at.utcoffset() == UTC.utcoffset(datetime.now(UTC))


@pytest.mark.asyncio
async def test_soft_delete_hides_food_from_active_list(
    db_session: AsyncSession, seeded_user_and_food: tuple[User, FoodRecord]
) -> None:
    user, food = seeded_user_and_food
    repository = FoodRepository(db_session)
    assert await repository.soft_delete(food.id, user.id) is True
    assert await repository.list_for_user(user.id, include_deleted=False) == []
    assert [item.id for item in await repository.list_for_user(user.id, True)] == [food.id]


@pytest.mark.asyncio
async def test_idempotency_rejects_same_key_with_changed_request(
    db_session: AsyncSession, seeded_user: User
) -> None:
    repository = IdempotencyRepository(db_session)
    await repository.begin(seeded_user.id, "/foods/manual", "key-1", "hash-a")
    with pytest.raises(IdempotencyConflict):
        await repository.begin(seeded_user.id, "/foods/manual", "key-1", "hash-b")


@pytest.mark.asyncio
async def test_idempotency_complete_and_replay_are_scoped(
    db_session: AsyncSession, seeded_user: User
) -> None:
    other = await UserRepository(db_session).get_or_create_by_openid("mock:other")
    repository = IdempotencyRepository(db_session)
    await repository.begin(seeded_user.id, "/foods/manual", "key-1", "hash-a")
    completed = await repository.complete(
        seeded_user.id,
        "/foods/manual",
        "key-1",
        "hash-a",
        response_status=201,
        response_resource_id="42",
        response_json={"id": 42},
    )
    replay = await repository.get_replay(
        seeded_user.id, "/foods/manual", "key-1", "hash-a"
    )
    assert completed.status == "completed"
    assert replay is not None
    assert (replay.response_status, replay.response_resource_id, replay.response_json) == (
        201,
        "42",
        {"id": 42},
    )
    assert await repository.get_replay(other.id, "/foods/manual", "key-1", "hash-a") is None


@pytest.mark.asyncio
async def test_idempotency_bounds_stored_response_json(
    db_session: AsyncSession, seeded_user: User
) -> None:
    repository = IdempotencyRepository(db_session)
    await repository.begin(seeded_user.id, "/foods/manual", "large", "hash-a")
    with pytest.raises(IdempotencyResponseTooLarge):
        await repository.complete(
            seeded_user.id,
            "/foods/manual",
            "large",
            "hash-a",
            response_status=201,
            response_resource_id=None,
            response_json={"value": "界" * 6_000},
        )


@pytest.mark.asyncio
async def test_migration_seeds_exactly_70_enabled_v1_rules(
    db_session: AsyncSession,
) -> None:
    count = await db_session.scalar(
        select(func.count()).select_from(PreservationRuleModel).where(
            PreservationRuleModel.rule_version == "v1",
            PreservationRuleModel.enabled.is_(True),
        )
    )
    assert count == 70
    rule = await RuleRepository(db_session).find_by_name("牛奶")
    assert rule is not None
    assert rule.food_name == "鲜牛奶"
