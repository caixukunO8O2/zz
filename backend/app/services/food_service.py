"""Food creation, recalculation, ownership, and presentation use cases."""

from datetime import date

from app.core.errors import APIError
from app.domain.date_rules import (
    DateCalculation,
    DateRuleError,
    MissingDateBasisError,
    calculate_consume_by,
    freshness_bucket,
)
from app.domain.foods import DateBasis, FoodLifecycle, FreshnessBucket, StorageType
from app.models.entities import FoodRecord, PreservationRuleModel
from app.repositories.foods import UNSET, FoodCreateData, FoodRepository, FoodUpdateData
from app.repositories.rules import RuleRepository
from app.schemas.foods import FoodManualCreate, FoodPatch, FoodRead


class FoodService:
    def __init__(
        self,
        foods: FoodRepository,
        rules: RuleRepository,
        *,
        today: date,
    ) -> None:
        self._foods = foods
        self._rules = rules
        self._today = today

    @staticmethod
    def _knowledge_days(
        rule: PreservationRuleModel | None, storage_type: StorageType
    ) -> int | None:
        if rule is None:
            return None
        if storage_type is StorageType.ROOM:
            return rule.room_days
        if storage_type is StorageType.CHILLED:
            return rule.chilled_days
        return rule.frozen_days

    async def _calculation(
        self,
        *,
        food_name: str,
        storage_type: StorageType,
        added_on: date,
        declared_expiry_date: date | None,
        production_date: date | None,
        shelf_life_days: int | None,
        manual_consume_by: date | None,
    ) -> tuple[DateCalculation, PreservationRuleModel | None]:
        rule = await self._rules.find_by_name(food_name)
        try:
            calculation = calculate_consume_by(
                declared_expiry_date,
                production_date,
                shelf_life_days,
                added_on,
                self._knowledge_days(rule, storage_type),
                manual_consume_by=manual_consume_by,
            )
        except MissingDateBasisError as exc:
            raise APIError(
                422,
                "missing_date_basis",
                "请设置建议食用日期",
            ) from exc
        except DateRuleError as exc:
            raise APIError(422, "invalid_food_dates", "食品日期不正确") from exc
        if calculation.conflict:
            raise APIError(422, "date_conflict", "包装日期存在冲突，请确认后再保存")
        return calculation, rule

    async def create_manual(self, user_id: int, payload: FoodManualCreate) -> FoodRecord:
        calculation, rule = await self._calculation(
            food_name=payload.food_name,
            storage_type=payload.storage_type,
            added_on=payload.added_on,
            declared_expiry_date=payload.declared_expiry_date,
            production_date=payload.production_date,
            shelf_life_days=payload.shelf_life_days,
            manual_consume_by=payload.recommended_consume_by,
        )
        return await self._foods.create(
            user_id,
            FoodCreateData(
                food_name=payload.food_name,
                brand=payload.brand,
                category=payload.category or (rule.category if rule is not None else None),
                thumbnail_path=payload.thumbnail_path,
                production_date=payload.production_date,
                declared_expiry_date=payload.declared_expiry_date,
                shelf_life_days=payload.shelf_life_days,
                storage_type=payload.storage_type,
                added_on=payload.added_on,
                recommended_consume_by=calculation.consume_by,
                date_basis=calculation.basis,
            ),
        )

    async def list_for_user(
        self, user_id: int, bucket: FreshnessBucket | None
    ) -> list[FoodRecord]:
        records = await self._foods.list_for_user(user_id)
        if bucket is None:
            return records
        return [
            record
            for record in records
            if freshness_bucket(record.recommended_consume_by, self._today) is bucket
        ]

    async def get_for_user(self, food_id: int, user_id: int) -> FoodRecord:
        record = await self._foods.get_for_user(food_id, user_id)
        if record is None or record.lifecycle_status == FoodLifecycle.DELETED.value:
            raise APIError(404, "food_not_found", "没有找到这项食材")
        return record

    async def update(
        self, food_id: int, user_id: int, payload: FoodPatch
    ) -> FoodRecord:
        record = await self._foods.get_for_user(food_id, user_id, for_update=True)
        if record is None or record.lifecycle_status == FoodLifecycle.DELETED.value:
            raise APIError(404, "food_not_found", "没有找到这项食材")
        fields = payload.model_fields_set
        food_name = payload.food_name if "food_name" in fields else record.food_name
        storage_type = (
            payload.storage_type
            if "storage_type" in fields
            else StorageType(record.storage_type)
        )
        added_on = payload.added_on if "added_on" in fields else record.added_on
        if food_name is None or storage_type is None or added_on is None:
            raise APIError(422, "validation_error", "请求参数不正确")
        production_date = (
            payload.production_date
            if "production_date" in fields
            else record.production_date
        )
        declared_expiry_date = (
            payload.declared_expiry_date
            if "declared_expiry_date" in fields
            else record.declared_expiry_date
        )
        shelf_life_days = (
            payload.shelf_life_days
            if "shelf_life_days" in fields
            else record.shelf_life_days
        )
        manual_consume_by = None
        if "recommended_consume_by" in fields:
            manual_consume_by = payload.recommended_consume_by
        elif record.date_basis == DateBasis.MANUAL_USER_SET.value:
            manual_consume_by = record.recommended_consume_by
        calculation, _ = await self._calculation(
            food_name=food_name,
            storage_type=storage_type,
            added_on=added_on,
            declared_expiry_date=declared_expiry_date,
            production_date=production_date,
            shelf_life_days=shelf_life_days,
            manual_consume_by=manual_consume_by,
        )
        data = FoodUpdateData(
            food_name=food_name if "food_name" in fields else UNSET,
            brand=payload.brand if "brand" in fields else UNSET,
            category=payload.category if "category" in fields else UNSET,
            thumbnail_path=(
                payload.thumbnail_path
                if "thumbnail_path" in fields
                else UNSET
            ),
            production_date=(
                payload.production_date if "production_date" in fields else UNSET
            ),
            declared_expiry_date=(
                payload.declared_expiry_date
                if "declared_expiry_date" in fields
                else UNSET
            ),
            shelf_life_days=(
                payload.shelf_life_days if "shelf_life_days" in fields else UNSET
            ),
            storage_type=(
                storage_type if "storage_type" in fields else UNSET
            ),
            added_on=added_on if "added_on" in fields else UNSET,
            recommended_consume_by=calculation.consume_by,
            date_basis=calculation.basis,
        )
        updated = await self._foods.update(food_id, user_id, data)
        if updated is None:  # pragma: no cover - locked to the prior ownership read
            raise APIError(404, "food_not_found", "没有找到这项食材")
        return updated

    async def soft_delete(self, food_id: int, user_id: int) -> None:
        if not await self._foods.soft_delete(food_id, user_id):
            raise APIError(404, "food_not_found", "没有找到这项食材")

    def present(self, record: FoodRecord) -> FoodRead:
        return FoodRead(
            id=record.id,
            food_name=record.food_name,
            brand=record.brand,
            category=record.category,
            thumbnail_path=record.thumbnail_path,
            production_date=record.production_date,
            declared_expiry_date=record.declared_expiry_date,
            shelf_life_days=record.shelf_life_days,
            storage_type=StorageType(record.storage_type),
            added_on=record.added_on,
            recommended_consume_by=record.recommended_consume_by,
            date_basis=DateBasis(record.date_basis),
            freshness_bucket=freshness_bucket(
                record.recommended_consume_by, self._today
            ),
        )
