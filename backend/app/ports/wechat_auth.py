"""Provider-neutral WeChat authentication boundary."""

from dataclasses import dataclass
from typing import Protocol

MOCK_OPENID_PREFIX = "mock:"
MAX_OPENID_LENGTH = 128
MAX_WECHAT_CODE_LENGTH = MAX_OPENID_LENGTH - len(MOCK_OPENID_PREFIX)


class WechatAuthUnavailable(RuntimeError):
    """Raised when the configured identity provider cannot serve the request."""


class InvalidWechatIdentity(ValueError):
    """Raised when a provider returns an identity unsafe for local persistence."""


@dataclass(frozen=True, slots=True)
class WechatIdentity:
    openid: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.openid, str)
            or not self.openid.strip()
            or len(self.openid) > MAX_OPENID_LENGTH
        ):
            raise InvalidWechatIdentity(
                f"openid must be nonblank and at most {MAX_OPENID_LENGTH} characters"
            )


def validate_wechat_identity(identity: object) -> WechatIdentity:
    """Revalidate provider output before it crosses into persistence."""
    openid = getattr(identity, "openid", None)
    if not isinstance(openid, str):
        raise InvalidWechatIdentity("provider identity must contain a string openid")
    return WechatIdentity(openid=openid)


class WechatAuthPort(Protocol):
    def exchange_code(self, code: str) -> WechatIdentity:
        """Exchange a short-lived WeChat code for a stable identity."""
        ...
