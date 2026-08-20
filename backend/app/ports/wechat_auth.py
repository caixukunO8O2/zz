"""Provider-neutral WeChat authentication boundary."""

from dataclasses import dataclass
from typing import Protocol

MOCK_OPENID_PREFIX = "mock:"
MAX_OPENID_LENGTH = 128
MAX_WECHAT_CODE_LENGTH = MAX_OPENID_LENGTH - len(MOCK_OPENID_PREFIX)


class WechatAuthUnavailable(RuntimeError):
    """Raised when the configured identity provider cannot serve the request."""


@dataclass(frozen=True, slots=True)
class WechatIdentity:
    openid: str


class WechatAuthPort(Protocol):
    def exchange_code(self, code: str) -> WechatIdentity:
        """Exchange a short-lived WeChat code for a stable identity."""
        ...
