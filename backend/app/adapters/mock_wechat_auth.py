"""Deterministic WeChat identity adapter used only in mock mode."""

from app.ports.wechat_auth import WechatIdentity


class MockWechatAuthUnavailable(RuntimeError):
    """Raised when the mock adapter is invoked outside mock mode."""


class MockWechatAuthAdapter:
    def __init__(self, app_mode: str) -> None:
        self._app_mode = app_mode

    def exchange_code(self, code: str) -> WechatIdentity:
        if self._app_mode != "mock":
            raise MockWechatAuthUnavailable("mock WeChat auth requires APP_MODE=mock")
        return WechatIdentity(openid=f"mock:{code}")
