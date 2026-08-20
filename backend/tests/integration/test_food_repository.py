import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import CHAR, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.entities import FoodRecord, PreservationRuleModel, User
from app.models.idempotency import IdempotencyRecord
from app.repositories.foods import FoodCreateData, FoodRepository, FoodUpdateData
from app.repositories.idempotency import (
    IdempotencyBeginResult,
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


class _FakeDatabaseSession:
    def __init__(self, database_name: str | None) -> None:
        self.database_name = database_name
        self.scalar_calls = 0
        self.execute_calls = 0

    async def scalar(self, statement: object) -> str | None:
        self.scalar_calls += 1
        return self.database_name

    async def execute(self, statement: object) -> None:
        self.execute_calls += 1


async def _require_test_database(
    session: AsyncSession | _FakeDatabaseSession,
) -> None:
    database_name = await session.scalar(text("SELECT DATABASE()"))
    if database_name != "xianzhi_test":
        raise RuntimeError(
            f"refusing integration-test cleanup on database {database_name!r}"
        )


async def _clean_test_database(
    session: AsyncSession | _FakeDatabaseSession,
) -> None:
    await _require_test_database(session)
    for model in (IdempotencyRecord, FoodRecord, User):
        await session.execute(delete(model))


@pytest.mark.asyncio
async def test_cleanup_guard_rejects_every_database_except_exact_test_name() -> None:
    for unsafe_name in ("xianzhi", "xianzhi_test_backup", None):
        unsafe_session = _FakeDatabaseSession(unsafe_name)
        with pytest.raises(RuntimeError, match="refusing integration-test cleanup"):
            await _clean_test_database(unsafe_session)
        assert unsafe_session.scalar_calls == 1
        assert unsafe_session.execute_calls == 0

    safe_session = _FakeDatabaseSession("xianzhi_test")
    await _clean_test_database(safe_session)
    assert safe_session.scalar_calls == 1
    assert safe_session.execute_calls == 3


def test_scan_linked_id_uses_fixed_width_uuid_storage() -> None:
    column_type = FoodRecord.__table__.c.scan_session_id.type
    assert isinstance(column_type, CHAR)
    assert column_type.length == 36


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await _clean_test_database(session)
        await session.commit()
    yield session_factory
    async with session_factory() as session:
        await _clean_test_database(session)
        await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with db_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_user(db_session: AsyncSession) -> User:
    return await UserRepository(db_session).get_or_create_by_openid("mock:seeded")


@pytest.mark.asyncio
async def test_user_get_or_create_is_atomic_under_repeatable_read(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    start = asyncio.Event()

    async def create_user() -> int:
        async with db_session_factory() as session:
            await start.wait()
            user = await UserRepository(session).get_or_create_by_openid("mock:race")
            await session.commit()
            return user.id

    callers = [asyncio.create_task(create_user()) for _ in range(2)]
    await asyncio.sleep(0)
    start.set()
    user_ids = await asyncio.gather(*callers)

    assert user_ids[0] == user_ids[1]
    async with db_session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.openid == "mock:race")
        )
    assert count == 1


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
async def test_idempotency_begin_same_hash_has_exactly_one_concurrent_owner(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        user = await UserRepository(session).get_or_create_by_openid("mock:idem-same")
        await session.commit()
        user_id = user.id

    start = asyncio.Event()

    async def begin() -> tuple[bool, int]:
        async with db_session_factory() as session:
            await start.wait()
            result = await IdempotencyRepository(session).begin(
                user_id, "/foods/manual", "same", "hash-a"
            )
            await session.commit()
            return result.acquired, result.record.id

    callers = [asyncio.create_task(begin()) for _ in range(2)]
    await asyncio.sleep(0)
    start.set()
    results = await asyncio.gather(*callers)

    assert sorted(acquired for acquired, _ in results) == [False, True]
    assert len({record_id for _, record_id in results}) == 1


@pytest.mark.asyncio
async def test_idempotency_begin_different_hash_has_stable_concurrent_conflict(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        user = await UserRepository(session).get_or_create_by_openid("mock:idem-different")
        await session.commit()
        user_id = user.id

    start = asyncio.Event()

    async def begin(request_hash: str) -> IdempotencyBeginResult | BaseException:
        async with db_session_factory() as session:
            await start.wait()
            try:
                result = await IdempotencyRepository(session).begin(
                    user_id, "/foods/manual", "different", request_hash
                )
                await session.commit()
                return result
            except BaseException as exc:
                await session.rollback()
                return exc

    callers = [
        asyncio.create_task(begin("hash-a")),
        asyncio.create_task(begin("hash-b")),
    ]
    await asyncio.sleep(0)
    start.set()
    results = await asyncio.gather(*callers)

    owners: list[IdempotencyBeginResult] = []
    conflicts: list[IdempotencyConflict] = []
    for result in results:
        if isinstance(result, IdempotencyConflict):
            conflicts.append(result)
        elif isinstance(result, BaseException):
            pytest.fail(f"unexpected idempotency exception: {result!r}")
        else:
            owners.append(result)
    assert len(owners) == 1
    assert owners[0].acquired is True
    assert len(conflicts) == 1


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
async def test_idempotency_uses_mysql_json_storage_size_for_boundary(
    db_session: AsyncSession, seeded_user: User
) -> None:
    response_json: dict[str, object] = {"value": "a" * 16_368}
    compact_size = len(
        json.dumps(response_json, ensure_ascii=False, separators=(",", ":")).encode()
    )
    assert compact_size < 16_384

    repository = IdempotencyRepository(db_session)
    await repository.begin(seeded_user.id, "/foods/manual", "mysql-size", "hash-a")
    with pytest.raises(IdempotencyResponseTooLarge):
        await repository.complete(
            seeded_user.id,
            "/foods/manual",
            "mysql-size",
            "hash-a",
            response_status=201,
            response_resource_id=None,
            response_json=response_json,
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
