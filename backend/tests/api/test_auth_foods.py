import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token
from app.main import create_app
from app.models.entities import FoodRecord, User
from app.models.idempotency import IdempotencyRecord

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi_test",
)
TEST_JWT_SECRET = "test-secret-material-with-at-least-sixty-four-bytes-for-hmac-sha256"


async def _clean_test_database(session: AsyncSession) -> None:
    database_name = await session.scalar(text("SELECT DATABASE()"))
    if database_name != "xianzhi_test":
        raise RuntimeError(
            f"refusing API-test cleanup on database {database_name!r}"
        )
    for model in (IdempotencyRecord, FoodRecord, User):
        await session.execute(delete(model))


@pytest_asyncio.fixture
async def api_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _clean_test_database(session)
        await session.commit()
    yield factory
    async with factory() as session:
        await _clean_test_database(session)
        await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    api_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
    )
    transport = ASGITransport(
        app=create_app(settings, session_factory=api_session_factory)
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as value:
        yield value


async def _login(client: AsyncClient, code: str) -> str:
    response = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return str(response.json()["access_token"])


async def _auth_headers(client: AsyncClient, code: str = "owner") -> dict[str, str]:
    return {"Authorization": f"Bearer {await _login(client, code)}"}


async def _create_food(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    key: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    body = payload or {
        "food_name": "草莓",
        "category": "fruit",
        "storage_type": "chilled",
        "added_on": "2026-08-20",
    }
    response = await client.post(
        "/api/v1/foods/manual",
        json=body,
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


@pytest.mark.asyncio
async def test_mock_login_returns_seven_day_hs256_bearer_token(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/wechat/login", json={"code": "demo-user"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    claims = jwt.decode(
        body["access_token"],
        TEST_JWT_SECRET,
        algorithms=["HS256"],
    )
    assert isinstance(claims["sub"], str)
    assert claims["exp"] - claims["iat"] == 7 * 24 * 60 * 60


def test_token_decode_accepts_only_hs256_and_rejects_expired_tokens() -> None:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    token = create_access_token(42, TEST_JWT_SECRET, now=now)
    claims = decode_access_token(token, TEST_JWT_SECRET, now=now + timedelta(days=1))
    assert claims.user_id == 42

    hs384 = jwt.encode(
        {"sub": "42", "iat": now, "exp": now + timedelta(days=7)},
        TEST_JWT_SECRET,
        algorithm="HS384",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(hs384, TEST_JWT_SECRET, now=now)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, TEST_JWT_SECRET, now=now + timedelta(days=8))


@pytest.mark.asyncio
async def test_mock_login_is_unavailable_outside_mock_mode(
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        app_mode="real",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
    )
    transport = ASGITransport(
        app=create_app(settings, session_factory=api_session_factory)
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as real_client:
        response = await real_client.post(
            "/api/v1/auth/wechat/login", json={"code": "demo-user"}
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "wechat_auth_unavailable",
            "message": "微信登录当前不可用",
            "retryable": False,
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "expected_code"),
    [
        (None, "authentication_required"),
        ("not-bearer", "invalid_token"),
        ("Bearer malformed", "invalid_token"),
    ],
)
async def test_food_list_rejects_missing_or_malformed_authorization(
    client: AsyncClient,
    authorization: str | None,
    expected_code: str,
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}
    response = await client.get("/api/v1/foods", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": expected_code,
        "message": "请先登录" if authorization is None else "登录状态无效",
        "retryable": False,
    }


@pytest.mark.asyncio
async def test_food_list_rejects_expired_token(client: AsyncClient) -> None:
    expired = create_access_token(
        999,
        TEST_JWT_SECRET,
        now=datetime.now(UTC) - timedelta(days=8),
    )
    response = await client.get(
        "/api/v1/foods", headers={"Authorization": f"Bearer {expired}"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


@pytest.mark.asyncio
async def test_profile_can_be_read_updated_and_is_validated(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    initial = await client.get("/api/v1/users/me", headers=headers)
    updated = await client.patch(
        "/api/v1/users/me/profile",
        json={"nickname": "小鲜", "avatar_url": "https://example.test/avatar.png"},
        headers=headers,
    )
    invalid = await client.patch(
        "/api/v1/users/me/profile", json={"nickname": "   "}, headers=headers
    )

    assert initial.status_code == 200
    assert initial.json()["nickname"] is None
    assert updated.status_code == 200
    assert updated.json()["nickname"] == "小鲜"
    assert updated.json()["avatar_url"] == "https://example.test/avatar.png"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_manual_strawberry_uses_knowledge_rule_and_replays_exactly(
    client: AsyncClient, api_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    headers = await _auth_headers(client)
    request_headers = {**headers, "Idempotency-Key": "food-1"}
    payload = {
        "food_name": "草莓",
        "category": "fruit",
        "storage_type": "chilled",
        "added_on": "2026-08-20",
    }
    first = await client.post(
        "/api/v1/foods/manual", json=payload, headers=request_headers
    )
    replay = await client.post(
        "/api/v1/foods/manual", json=payload, headers=request_headers
    )

    assert (first.status_code, replay.status_code) == (201, 201)
    assert replay.json() == first.json()
    assert first.json()["recommended_consume_by"] == "2026-08-25"
    assert first.json()["date_basis"] == "knowledge_base_estimate"
    async with api_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(FoodRecord)) == 1


@pytest.mark.asyncio
async def test_manual_create_same_key_with_changed_payload_is_conflict(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    request_headers = {**headers, "Idempotency-Key": "changed-food"}
    first = await client.post(
        "/api/v1/foods/manual",
        json={
            "food_name": "草莓",
            "storage_type": "chilled",
            "added_on": "2026-08-20",
        },
        headers=request_headers,
    )
    conflict = await client.post(
        "/api/v1/foods/manual",
        json={
            "food_name": "草莓",
            "storage_type": "frozen",
            "added_on": "2026-08-20",
        },
        headers=request_headers,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


@pytest.mark.asyncio
async def test_manual_unknown_food_requires_or_uses_manual_date(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    base = {
        "food_name": "自制果酱",
        "storage_type": "chilled",
        "added_on": "2026-08-20",
    }
    missing = await client.post(
        "/api/v1/foods/manual",
        json=base,
        headers={**headers, "Idempotency-Key": "manual-missing"},
    )
    supplied = await client.post(
        "/api/v1/foods/manual",
        json={**base, "recommended_consume_by": "2026-08-30"},
        headers={**headers, "Idempotency-Key": "manual-supplied"},
    )

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "missing_date_basis"
    assert supplied.status_code == 201
    assert supplied.json()["recommended_consume_by"] == "2026-08-30"
    assert supplied.json()["date_basis"] == "manual_user_set"


@pytest.mark.asyncio
async def test_manual_create_rejects_conflicting_packaged_dates(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/foods/manual",
        json={
            "food_name": "鲜牛奶",
            "storage_type": "chilled",
            "added_on": "2026-08-20",
            "production_date": "2026-08-18",
            "shelf_life_days": 7,
            "declared_expiry_date": "2026-08-24",
        },
        headers={**headers, "Idempotency-Key": "date-conflict"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_conflict"


@pytest.mark.asyncio
async def test_food_routes_enforce_cross_user_404_isolation(client: AsyncClient) -> None:
    owner = await _auth_headers(client, "owner")
    stranger = await _auth_headers(client, "stranger")
    food = await _create_food(client, owner, key="owned-food")
    food_id = food["id"]

    read = await client.get(f"/api/v1/foods/{food_id}", headers=stranger)
    patch = await client.patch(
        f"/api/v1/foods/{food_id}", json={"brand": "越权"}, headers=stranger
    )
    delete_response = await client.delete(
        f"/api/v1/foods/{food_id}",
        headers={**stranger, "Idempotency-Key": "stranger-delete"},
    )

    assert read.status_code == patch.status_code == delete_response.status_code == 404
    assert read.json() == {
        "error": {
            "code": "food_not_found",
            "message": "没有找到这项食材",
            "retryable": False,
        }
    }


@pytest.mark.asyncio
async def test_food_list_valid_empty_bucket_and_bucket_filter(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    empty = await client.get("/api/v1/foods?bucket=expired", headers=headers)
    today = date.today()
    await _create_food(
        client,
        headers,
        key="expired-food",
        payload={
            "food_name": "旧罐头",
            "storage_type": "room",
            "added_on": today.isoformat(),
            "declared_expiry_date": (today - timedelta(days=1)).isoformat(),
        },
    )
    filtered = await client.get("/api/v1/foods?bucket=expired", headers=headers)

    assert empty.status_code == 200
    assert empty.json() == {"items": []}
    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 1
    assert filtered.json()["items"][0]["freshness_bucket"] == "expired"


@pytest.mark.asyncio
async def test_patch_recalculates_and_clears_explicit_nullable_field_only(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    food = await _create_food(
        client,
        headers,
        key="patch-food",
        payload={
            "food_name": "草莓",
            "brand": "果园牌",
            "category": "fruit",
            "storage_type": "chilled",
            "added_on": "2026-08-20",
        },
    )
    response = await client.patch(
        f"/api/v1/foods/{food['id']}",
        json={"storage_type": "frozen", "brand": None},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_consume_by"] == "2026-09-19"
    assert body["date_basis"] == "knowledge_base_estimate"
    assert body["brand"] is None
    assert body["category"] == "fruit"


@pytest.mark.asyncio
async def test_delete_soft_deletes_and_replays_204(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    food = await _create_food(client, headers, key="delete-target")
    delete_headers = {**headers, "Idempotency-Key": "delete-food-1"}

    first = await client.delete(
        f"/api/v1/foods/{food['id']}", headers=delete_headers
    )
    replay = await client.delete(
        f"/api/v1/foods/{food['id']}", headers=delete_headers
    )
    read = await client.get(f"/api/v1/foods/{food['id']}", headers=headers)
    listed = await client.get("/api/v1/foods", headers=headers)

    assert first.status_code == replay.status_code == 204
    assert first.content == replay.content == b""
    assert read.status_code == 404
    assert listed.json() == {"items": []}


@pytest.mark.asyncio
async def test_missing_idempotency_key_uses_stable_error_envelope(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/foods/manual",
        json={
            "food_name": "草莓",
            "storage_type": "chilled",
            "added_on": "2026-08-20",
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "idempotency_key_required",
            "message": "缺少幂等键",
            "retryable": False,
        }
    }
