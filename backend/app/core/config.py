from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict


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
        secret = settings.jwt_secret.strip()
        if (
            secret == "change-me-for-production"
            or len(secret.encode("utf-8")) < 32
            or len(set(secret)) < 8
        ):
            raise ValueError(
                "JWT signing secret must contain at least 32 nontrivial bytes "
                "outside mock mode"
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
