from typing import cast

import pytest

from app.adapters.mock_wechat_auth import MockWechatAuthAdapter
from app.core.errors import APIError
from app.models.entities import User
from app.ports.wechat_auth import (
    InvalidWechatIdentity,
    WechatAuthUnavailable,
    WechatIdentity,
)
from app.repositories.users import UserRepository
from app.services.auth_service import AuthService

UNIT_JWT_SECRET = "unit-test-hmac-secret-with-at-least-thirty-two-bytes"


class _ConfiguredIdentityProvider:
    def __init__(self, openid: str) -> None:
        self._openid = openid

    def exchange_code(self, code: str) -> WechatIdentity:
        return cast(WechatIdentity, _RawProviderIdentity(self._openid))


class _RawProviderIdentity:
    def __init__(self, openid: str) -> None:
        self.openid = openid


class _RecordingUsers:
    def __init__(self) -> None:
        self.openids: list[str] = []

    async def get_or_create_by_openid(self, openid: str) -> User:
        self.openids.append(openid)
        return User(id=23, openid=openid)


@pytest.mark.asyncio
async def test_auth_unavailable_contract_is_provider_neutral() -> None:
    adapter = MockWechatAuthAdapter("real")
    with pytest.raises(WechatAuthUnavailable):
        adapter.exchange_code("demo")

    service = AuthService(cast(UserRepository, object()), adapter)
    with pytest.raises(APIError) as captured:
        await service.login("demo", "unused-secret")

    assert captured.value.status_code == 503
    assert captured.value.code == "wechat_auth_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("openid", ["", "   ", "x" * 129])
async def test_invalid_provider_identity_is_rejected_before_repository(
    openid: str,
) -> None:
    users = _RecordingUsers()
    service = AuthService(
        cast(UserRepository, users),
        _ConfiguredIdentityProvider(openid),
    )

    with pytest.raises(APIError) as captured:
        await service.login("provider-code", UNIT_JWT_SECRET)

    assert captured.value.status_code == 502
    assert captured.value.code == "wechat_auth_invalid_response"
    assert users.openids == []


@pytest.mark.asyncio
async def test_provider_identity_accepts_exact_openid_storage_boundary() -> None:
    openid = "x" * 128
    users = _RecordingUsers()
    service = AuthService(
        cast(UserRepository, users),
        _ConfiguredIdentityProvider(openid),
    )

    token = await service.login("provider-code", UNIT_JWT_SECRET)

    assert isinstance(token, str)
    assert users.openids == [openid]


def test_identity_value_object_exposes_provider_neutral_validation_error() -> None:
    with pytest.raises(InvalidWechatIdentity):
        WechatIdentity(openid="")
