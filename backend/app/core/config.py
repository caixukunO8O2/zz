from functools import lru_cache
from pathlib import Path

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
