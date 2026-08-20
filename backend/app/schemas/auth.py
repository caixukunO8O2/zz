"""Authentication HTTP schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ports.wechat_auth import MAX_WECHAT_CODE_LENGTH


class WechatLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_WECHAT_CODE_LENGTH)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("code must not be blank")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
