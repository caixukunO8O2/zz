from datetime import date
from typing import cast

import pytest

from app.domain.foods import DateBasis, FoodLifecycle, StorageType
from app.models.entities import FoodRecord
from app.repositories.foods import FoodRepository, FoodUpdateData, UnsetType
from app.repositories.rules import RuleRepository
from app.schemas.foods import FoodPatch
from app.services.food_service import FoodService


class _CapturingFoods:
    def __init__(self, record: FoodRecord) -> None:
        self.record = record
        self.updated: FoodUpdateData | None = None

    async def get_for_user(
        self, food_id: int, user_id: int, *, for_update: bool = False
    ) -> FoodRecord | None:
        assert (food_id, user_id) == (self.record.id, self.record.user_id)
        assert for_update is True
        return self.record

    async def update(
        self, food_id: int, user_id: int, data: FoodUpdateData
    ) -> FoodRecord | None:
        self.updated = data
        if not isinstance(data.category, UnsetType):
            self.record.category = data.category
        return self.record


class _NoRules:
    async def find_by_name(self, food_name: str) -> None:
        return None


@pytest.mark.asyncio
async def test_patch_passes_omitted_nullable_fields_as_repository_unset() -> None:
    record = FoodRecord(
        id=12,
        user_id=34,
        food_name="自制果酱",
        brand="果园牌",
        category="fruit",
        thumbnail_path="stored.jpg",
        storage_type=StorageType.CHILLED.value,
        added_on=date(2026, 8, 20),
        recommended_consume_by=date(2026, 8, 30),
        date_basis=DateBasis.MANUAL_USER_SET.value,
        lifecycle_status=FoodLifecycle.ACTIVE.value,
    )
    foods = _CapturingFoods(record)
    service = FoodService(
        cast(FoodRepository, foods),
        cast(RuleRepository, _NoRules()),
        today=date(2026, 8, 20),
    )

    await service.update(record.id, record.user_id, FoodPatch(category="vegetable"))

    assert foods.updated is not None
    assert isinstance(foods.updated.brand, UnsetType)
    assert isinstance(foods.updated.thumbnail_path, UnsetType)
    assert foods.updated.category == "vegetable"
