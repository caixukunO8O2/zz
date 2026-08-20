import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token
from app.main import create_app
from app.models.entities import FoodRecord, User
from app.models.idempotency import IdempotencyRecord
from app.ports.wechat_auth import WechatIdentity

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://xianzhi:xianzhi@127.0.0.1:3306/xianzhi_test",
)
TEST_JWT_SECRET = (
    "aB3_dE5-fG7_hJ9-kL2_mN4-pQ6_rS8-tU0_vW1-xYz"
    "A7_cD9-eF2_gH4-jK6_mN8-pQ"
)
FIXED_NOW = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


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
    configured_app = create_app(
        settings,
        session_factory=api_session_factory,
        now_provider=lambda: FIXED_NOW,
    )
    transport = ASGITransport(app=configured_app)
    async with configured_app.router.lifespan_context(configured_app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as value:
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


class _CommitFailingSession(AsyncSession):
    async def commit(self) -> None:
        raise OperationalError("COMMIT", {}, RuntimeError("forced commit failure"))


class _ResponseStartProbe:
    def __init__(self, app, probe) -> None:
        self._app = app
        self._probe = probe

    async def __call__(self, scope, receive, send) -> None:
        async def send_with_probe(message) -> None:
            if message["type"] == "http.response.start":
                await self._probe()
            await send(message)

        await self._app(scope, receive, send_with_probe)


class _ConfiguredWechatProvider:
    def __init__(self, openid: str) -> None:
        self._openid = openid

    def exchange_code(self, code: str) -> WechatIdentity:
        return cast(WechatIdentity, _RawProviderIdentity(self._openid))


class _RawProviderIdentity:
    def __init__(self, openid: str) -> None:
        self.openid = openid


async def _provider_login_response(
    api_session_factory: async_sessionmaker[AsyncSession], openid: str
):
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
    )
    configured_app = create_app(settings, session_factory=api_session_factory)
    configured_app.state.wechat_auth = _ConfiguredWechatProvider(openid)
    transport = ASGITransport(app=configured_app, raise_app_exceptions=False)
    async with configured_app.router.lifespan_context(configured_app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as configured_client:
            return await configured_client.post(
                "/api/v1/auth/wechat/login", json={"code": "provider-code"}
            )


@pytest.mark.asyncio
async def test_commit_failure_cannot_emit_visible_login_success(
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    engine = api_session_factory.kw["bind"]
    assert isinstance(engine, AsyncEngine)
    failing_factory = async_sessionmaker(
        engine, class_=_CommitFailingSession, expire_on_commit=False
    )
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
    )
    transport = ASGITransport(
        app=create_app(settings, session_factory=failing_factory),
        raise_app_exceptions=False,
    )

    async with AsyncClient(transport=transport, base_url="http://testserver") as value:
        response = await value.post(
            "/api/v1/auth/wechat/login", json={"code": "commit-must-fail"}
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "数据库暂时不可用",
            "retryable": True,
        }
    }


@pytest.mark.asyncio
async def test_idempotency_lock_is_released_before_response_start(
    client: AsyncClient,
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    token = await _login(client, "lock-owner")
    probe_reached_unlocked_row = False

    async def probe() -> None:
        nonlocal probe_reached_unlocked_row
        async with api_session_factory() as session:
            await session.execute(text("SET SESSION innodb_lock_wait_timeout = 1"))
            try:
                await session.scalar(
                    select(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.route == "/foods/manual",
                        IdempotencyRecord.idempotency_key == "response-lock",
                    )
                    .with_for_update()
                )
            except OperationalError:
                await session.rollback()
                return
            await session.rollback()
            probe_reached_unlocked_row = True

    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = create_app(settings, session_factory=api_session_factory)
    transport = ASGITransport(app=_ResponseStartProbe(app, probe))
    async with AsyncClient(transport=transport, base_url="http://testserver") as value:
        response = await value.post(
            "/api/v1/foods/manual",
            json={
                "food_name": "草莓",
                "storage_type": "chilled",
                "added_on": "2026-08-20",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "response-lock",
            },
        )

    assert response.status_code == 201
    assert probe_reached_unlocked_row is True


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
        decode_access_token(token, TEST_JWT_SECRET, now=now + timedelta(days=7))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, TEST_JWT_SECRET, now=now + timedelta(days=8))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_mutation",
    [
        {"exp": 10**30},
        {"iat": "yesterday"},
        {"exp": [2026, 8, 27]},
        {"iat": True},
        {"nbf": []},
        {"nbf": 10**30},
        {"nbf": 2_000_000_000},
    ],
)
async def test_signed_malformed_or_extreme_claims_are_stable_invalid_token(
    client: AsyncClient,
    claim_mutation: dict[str, object],
) -> None:
    valid_token = await _login(client, "signed-mutation-user")
    valid_claims = jwt.decode(
        valid_token,
        TEST_JWT_SECRET,
        algorithms=["HS256"],
    )
    claims: dict[str, object] = {
        "sub": valid_claims["sub"],
        "iat": valid_claims["iat"],
        "exp": valid_claims["exp"],
    }
    claims.update(claim_mutation)
    malformed = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")

    response = await client.get(
        "/api/v1/foods",
        headers={"Authorization": f"Bearer {malformed}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_token",
            "message": "登录状态无效",
            "retryable": False,
        }
    }


@pytest.mark.asyncio
async def test_mock_login_code_respects_openid_storage_boundary(
    client: AsyncClient,
) -> None:
    exact = await client.post(
        "/api/v1/auth/wechat/login", json={"code": "x" * 123}
    )
    over = await client.post(
        "/api/v1/auth/wechat/login", json={"code": "x" * 124}
    )

    assert exact.status_code == 200
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
@pytest.mark.parametrize("openid", ["", "x" * 129])
async def test_login_rejects_invalid_provider_openid_with_stable_auth_error(
    api_session_factory: async_sessionmaker[AsyncSession], openid: str
) -> None:
    response = await _provider_login_response(api_session_factory, openid)

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "wechat_auth_invalid_response",
            "message": "微信登录返回了无效身份",
            "retryable": False,
        }
    }


@pytest.mark.asyncio
async def test_login_accepts_provider_openid_at_exact_storage_boundary(
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await _provider_login_response(api_session_factory, "x" * 128)

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_shelf_life_boundaries_and_calendar_overflow_are_stable(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client, "shelf-boundary-user")
    base = {
        "food_name": "边界测试食品",
        "storage_type": "room",
        "added_on": "2026-08-20",
        "production_date": "2026-08-18",
    }
    exact = await client.post(
        "/api/v1/foods/manual",
        json={**base, "shelf_life_days": 36_500},
        headers={**headers, "Idempotency-Key": "shelf-exact"},
    )
    over = await client.post(
        "/api/v1/foods/manual",
        json={**base, "shelf_life_days": 36_501},
        headers={**headers, "Idempotency-Key": "shelf-over"},
    )
    overflow = await client.post(
        "/api/v1/foods/manual",
        json={
            **base,
            "production_date": "9999-12-31",
            "shelf_life_days": 1,
        },
        headers={**headers, "Idempotency-Key": "calendar-overflow"},
    )

    assert exact.status_code == 201
    assert exact.json()["recommended_consume_by"] == "2126-07-25"
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "validation_error"
    assert overflow.status_code == 422
    assert overflow.json()["error"]["code"] == "invalid_food_dates"


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
async def test_custom_invalid_token_error_includes_bearer_challenge(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/foods", headers={"Authorization": "Bearer malformed"}
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


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

    stranger_list = await client.get("/api/v1/foods", headers=stranger)
    assert stranger_list.status_code == 200
    assert stranger_list.json() == {"items": []}


@pytest.mark.asyncio
async def test_food_list_valid_empty_bucket_and_bucket_filter(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    empty = await client.get("/api/v1/foods?bucket=expired", headers=headers)
    today = FIXED_NOW.date()
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
async def test_patch_added_on_recalculates_from_persisted_calendar_date(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client, "added-on-owner")
    food = await _create_food(client, headers, key="added-on-food")

    response = await client.patch(
        f"/api/v1/foods/{food['id']}",
        json={"added_on": "2026-08-21"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["added_on"] == "2026-08-21"
    assert response.json()["recommended_consume_by"] == "2026-08-26"


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


@pytest.mark.asyncio
async def test_delete_requires_idempotency_key_without_deleting(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client, "delete-key-owner")
    food = await _create_food(client, headers, key="delete-key-target")

    response = await client.delete(f"/api/v1/foods/{food['id']}", headers=headers)
    still_present = await client.get(f"/api/v1/foods/{food['id']}", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"
    assert still_present.status_code == 200


@pytest.mark.asyncio
async def test_bucket_uses_configured_timezone_and_injected_clock(
    api_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(
        app_mode="mock",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://127.0.0.1:6379/15",
        jwt_secret=TEST_JWT_SECRET,
        app_timezone="Asia/Shanghai",
    )
    fixed_now = datetime(2026, 8, 20, 16, 30, tzinfo=UTC)
    configured_app = create_app(
        settings,
        session_factory=api_session_factory,
        now_provider=lambda: fixed_now,
    )
    transport = ASGITransport(app=configured_app)
    async with configured_app.router.lifespan_context(configured_app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as configured_client:
            headers = await _auth_headers(configured_client, "timezone-owner")
            await _create_food(
                configured_client,
                headers,
                key="timezone-food",
                payload={
                    "food_name": "时区食品",
                    "storage_type": "room",
                    "added_on": "2026-08-20",
                    "declared_expiry_date": "2026-08-20",
                },
            )
            expired = await configured_client.get(
                "/api/v1/foods?bucket=expired", headers=headers
            )

    assert expired.status_code == 200
    assert len(expired.json()["items"]) == 1
