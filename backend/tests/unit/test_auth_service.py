from typing import cast

import pytest

from app.adapters.mock_wechat_auth import MockWechatAuthAdapter
from app.core.errors import APIError
from app.ports.wechat_auth import WechatAuthUnavailable
from app.repositories.users import UserRepository
from app.services.auth_service import AuthService


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
