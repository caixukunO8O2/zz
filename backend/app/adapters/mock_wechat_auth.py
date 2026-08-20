"""Deterministic WeChat identity adapter used only in mock mode."""

from app.ports.wechat_auth import (
    MOCK_OPENID_PREFIX,
    WechatAuthUnavailable,
    WechatIdentity,
)


class MockWechatAuthAdapter:
    def __init__(self, app_mode: str) -> None:
        self._app_mode = app_mode

    def exchange_code(self, code: str) -> WechatIdentity:
        if self._app_mode != "mock":
            raise WechatAuthUnavailable("mock WeChat auth requires APP_MODE=mock")
        return WechatIdentity(openid=f"{MOCK_OPENID_PREFIX}{code}")
