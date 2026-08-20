"""Provider-neutral WeChat authentication boundary."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WechatIdentity:
    openid: str


class WechatAuthPort(Protocol):
    def exchange_code(self, code: str) -> WechatIdentity:
        """Exchange a short-lived WeChat code for a stable identity."""
        ...
