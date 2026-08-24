"""HTTP schemas for the scan-session lifecycle."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.date_rules import MAX_SHELF_LIFE_DAYS
from app.domain.foods import StorageType
from app.domain.scans import ImagePurpose, ScanStatus
from app.schemas.foods import FoodCategory, FoodRead

MockScenario = Literal["packaged_success", "needs_identity", "fresh_produce"]


class ScanSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mock_scenario: MockScenario | None = None


class ScanImageRead(BaseModel):
    id: int
    purpose: ImagePurpose
    analysis_status: str


class ScanFrameRead(ScanImageRead):
    duplicate: bool


class ScanSessionRead(BaseModel):
    id: str
    status: ScanStatus
    detected_fields: dict[str, object]
    conflicts: list[dict[str, object]]
    missing_fields: list[str]
    next_guidance: str
    expires_at: datetime
    images: list[ScanImageRead]


class ScanFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_name: str | None = Field(default=None, min_length=1, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    category: FoodCategory | None = None
    production_date: date | None = None
    declared_expiry_date: date | None = None
    shelf_life_days: int | None = Field(
        default=None, ge=0, le=MAX_SHELF_LIFE_DAYS
    )
    storage_type: StorageType | None = None
    recommended_consume_by: date | None = None
    date_conflict_choice: Literal["existing", "candidate"] | None = None

    @field_validator("food_name")
    @classmethod
    def normalize_food_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("food name must not be blank")
        return normalized


class ScanFinalizeResponse(BaseModel):
    food: FoodRead
