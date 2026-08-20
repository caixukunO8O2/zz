"""Issue and validate application-owned HS256 session tokens."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

TOKEN_LIFETIME = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: int
    issued_at: datetime
    expires_at: datetime


def create_access_token(
    user_id: int,
    secret: str,
    *,
    now: datetime | None = None,
) -> str:
    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    expires_at = issued_at + TOKEN_LIFETIME
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def decode_access_token(
    token: str,
    secret: str,
    *,
    now: datetime | None = None,
) -> AccessTokenClaims:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={
            "require": ["sub", "iat", "exp"],
            "verify_exp": False,
            "verify_iat": False,
        },
    )
    subject = payload["sub"]
    if not isinstance(subject, str) or not subject.isdecimal() or int(subject) <= 0:
        raise jwt.exceptions.InvalidSubjectError(
            "token subject must be a positive user id"
        )
    issued_timestamp = payload["iat"]
    expires_timestamp = payload["exp"]
    if (
        not isinstance(issued_timestamp, int)
        or isinstance(issued_timestamp, bool)
        or not isinstance(expires_timestamp, int)
        or isinstance(expires_timestamp, bool)
    ):
        raise jwt.InvalidTokenError("token timestamps must be integers")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        issued_at = datetime.fromtimestamp(issued_timestamp, UTC)
        expires_at = datetime.fromtimestamp(expires_timestamp, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise jwt.InvalidTokenError("token timestamps are out of range") from exc
    if expires_timestamp <= issued_timestamp:
        raise jwt.InvalidTokenError("token expiry must follow issuance")
    if current >= expires_at:
        raise jwt.ExpiredSignatureError("token has expired")
    if issued_at > current:
        raise jwt.InvalidIssuedAtError("token was issued in the future")
    return AccessTokenClaims(int(subject), issued_at, expires_at)
