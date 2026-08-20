"""Current-user profile schemas."""

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class UserRead(BaseModel):
    id: int
    nickname: str | None
    avatar_url: str | None


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(default=None, max_length=64)
    avatar_url: HttpUrl | None = Field(default=None, max_length=512)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("nickname must not be blank")
        return normalized
