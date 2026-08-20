import re
from collections import Counter
from functools import lru_cache
from math import log2
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_GENERATED_SECRET_LENGTH = 43
MIN_SECRET_ALPHABET_SIZE = 16
MIN_SECRET_SHANNON_BITS_PER_CHARACTER = 4.0


def _is_periodic(value: str) -> bool:
    """Return whether value contains two cycles of a repeated prefix pattern."""
    if len(value) < 2:
        return False
    prefix_lengths = [0] * len(value)
    matched = 0
    for index in range(1, len(value)):
        while matched > 0 and value[index] != value[matched]:
            matched = prefix_lengths[matched - 1]
        if value[index] == value[matched]:
            matched += 1
        prefix_lengths[index] = matched
    minimal_period = len(value) - prefix_lengths[-1]
    return minimal_period <= len(value) // 2


def _looks_like_generated_urlsafe_secret(value: str) -> bool:
    """Conservatively accept secrets.token_urlsafe(32)-style signing material."""
    if (
        len(value) < MIN_GENERATED_SECRET_LENGTH
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        return False
    counts = Counter(value)
    if len(counts) < MIN_SECRET_ALPHABET_SIZE or _is_periodic(value):
        return False
    length = len(value)
    entropy = -sum(
        (count / length) * log2(count / length) for count in counts.values()
    )
    return entropy >= MIN_SECRET_SHANNON_BITS_PER_CHARACTER


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: str = "mock"
    database_url: str = "mysql+aiomysql://xianzhi:xianzhi@mysql:3306/xianzhi"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "change-me-for-production"
    upload_dir: Path = Path(".data/uploads")
    app_timezone: str = "Asia/Shanghai"
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_pre_expiry_template_id: str = ""
    wechat_due_day_template_id: str = ""
    dashscope_api_key: str = ""
    bailian_vision_model: str = ""
    paddleocr_model_dir: Path = Path(".data/models/paddleocr")


def validate_runtime_settings(settings: Settings) -> ZoneInfo:
    """Validate security and timezone settings before the app starts serving."""
    if settings.app_mode != "mock":
        secret = settings.jwt_secret
        if (
            secret != secret.strip()
            or secret == "change-me-for-production"
            or not _looks_like_generated_urlsafe_secret(secret)
        ):
            raise ValueError(
                "JWT signing secret must be generated URL-safe material "
                "equivalent to secrets.token_urlsafe(32) outside mock mode"
            )
    try:
        return ZoneInfo(settings.app_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"invalid application timezone: {settings.app_timezone!r}"
        ) from exc


@lru_cache
def get_settings() -> Settings:
    return Settings()
