"""Food management request and response schemas."""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.date_rules import MAX_SHELF_LIFE_DAYS
from app.domain.foods import DateBasis, FreshnessBucket, StorageType

FoodCategory = Literal["fruit", "vegetable", "meat", "dairy", "cooked"]


class FoodManualCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_name: str = Field(min_length=1, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    category: FoodCategory | None = None
    thumbnail_path: str | None = Field(default=None, max_length=512)
    production_date: date | None = None
    declared_expiry_date: date | None = None
    shelf_life_days: int | None = Field(
        default=None, ge=0, le=MAX_SHELF_LIFE_DAYS
    )
    storage_type: StorageType
    added_on: date
    recommended_consume_by: date | None = None

    @field_validator("food_name")
    @classmethod
    def normalize_food_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("food name must not be blank")
        return normalized


class FoodPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_name: str | None = Field(default=None, min_length=1, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    category: FoodCategory | None = None
    thumbnail_path: str | None = Field(default=None, max_length=512)
    production_date: date | None = None
    declared_expiry_date: date | None = None
    shelf_life_days: int | None = Field(
        default=None, ge=0, le=MAX_SHELF_LIFE_DAYS
    )
    storage_type: StorageType | None = None
    added_on: date | None = None
    recommended_consume_by: date | None = None

    @field_validator("food_name")
    @classmethod
    def normalize_food_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("food name must not be blank")
        return normalized

    @model_validator(mode="after")
    def reject_null_for_required_food_fields(self) -> Self:
        for field in ("food_name", "storage_type", "added_on"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class FoodRead(BaseModel):
    id: int
    food_name: str
    brand: str | None
    category: str | None
    thumbnail_path: str | None
    production_date: date | None
    declared_expiry_date: date | None
    shelf_life_days: int | None
    storage_type: StorageType
    added_on: date
    recommended_consume_by: date
    date_basis: DateBasis
    freshness_bucket: FreshnessBucket


class FoodList(BaseModel):
    items: list[FoodRead]
