"""User-scoped food-record persistence operations."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.foods import DateBasis, FoodLifecycle, StorageType
from app.models.base import utc_now
from app.models.entities import FoodRecord


@dataclass(frozen=True, slots=True)
class FoodCreateData:
    food_name: str
    storage_type: StorageType | str
    added_on: date
    recommended_consume_by: date
    date_basis: DateBasis | str
    scan_session_id: str | None = None
    brand: str | None = None
    category: str | None = None
    thumbnail_path: str | None = None
    production_date: date | None = None
    declared_expiry_date: date | None = None
    shelf_life_days: int | None = None
    confidence_summary: dict[str, object] | None = None


class UnsetType:
    """Marker distinguishing an omitted PATCH field from an explicit null."""

    __slots__ = ()


UNSET = UnsetType()


@dataclass(frozen=True, slots=True)
class FoodUpdateData:
    food_name: str | UnsetType = UNSET
    storage_type: StorageType | str | UnsetType = UNSET
    added_on: date | UnsetType = UNSET
    recommended_consume_by: date | UnsetType = UNSET
    date_basis: DateBasis | str | UnsetType = UNSET
    brand: str | None | UnsetType = UNSET
    category: str | None | UnsetType = UNSET
    thumbnail_path: str | None | UnsetType = UNSET
    production_date: date | None | UnsetType = UNSET
    declared_expiry_date: date | None | UnsetType = UNSET
    shelf_life_days: int | None | UnsetType = UNSET


class FoodRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: int, data: FoodCreateData) -> FoodRecord:
        record = FoodRecord(
            user_id=user_id,
            scan_session_id=data.scan_session_id,
            food_name=data.food_name,
            brand=data.brand,
            category=data.category,
            thumbnail_path=data.thumbnail_path,
            production_date=data.production_date,
            declared_expiry_date=data.declared_expiry_date,
            shelf_life_days=data.shelf_life_days,
            added_on=data.added_on,
            storage_type=StorageType(data.storage_type).value,
            recommended_consume_by=data.recommended_consume_by,
            date_basis=DateBasis(data.date_basis).value,
            confidence_summary=data.confidence_summary,
            lifecycle_status=FoodLifecycle.ACTIVE.value,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_for_user(
        self, user_id: int, include_deleted: bool = False
    ) -> list[FoodRecord]:
        statement = select(FoodRecord).where(FoodRecord.user_id == user_id)
        if not include_deleted:
            statement = statement.where(
                FoodRecord.lifecycle_status != FoodLifecycle.DELETED.value
            )
        statement = statement.order_by(FoodRecord.recommended_consume_by, FoodRecord.id)
        return list((await self._session.scalars(statement)).all())

    async def get_for_user(
        self, food_id: int, user_id: int, *, for_update: bool = False
    ) -> FoodRecord | None:
        statement = select(FoodRecord).where(
            FoodRecord.id == food_id,
            FoodRecord.user_id == user_id,
            FoodRecord.lifecycle_status != FoodLifecycle.DELETED.value,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        return await self._session.scalar(statement)

    async def update(
        self, food_id: int, user_id: int, data: FoodUpdateData
    ) -> FoodRecord | None:
        record = await self.get_for_user(food_id, user_id)
        if record is None or record.lifecycle_status == FoodLifecycle.DELETED.value:
            return None
        if not isinstance(data.food_name, UnsetType):
            record.food_name = data.food_name
        if not isinstance(data.storage_type, UnsetType):
            record.storage_type = StorageType(data.storage_type).value
        if not isinstance(data.added_on, UnsetType):
            record.added_on = data.added_on
        if not isinstance(data.recommended_consume_by, UnsetType):
            record.recommended_consume_by = data.recommended_consume_by
        if not isinstance(data.date_basis, UnsetType):
            record.date_basis = DateBasis(data.date_basis).value
        for field in (
            "brand",
            "category",
            "thumbnail_path",
            "production_date",
            "declared_expiry_date",
            "shelf_life_days",
        ):
            value = getattr(data, field)
            if not isinstance(value, UnsetType):
                setattr(record, field, value)
        record.updated_at = utc_now()
        await self._session.flush()
        return record

    async def soft_delete(self, food_id: int, user_id: int) -> bool:
        record = await self.get_for_user(food_id, user_id)
        if record is None or record.lifecycle_status == FoodLifecycle.DELETED.value:
            return False
        deleted_at = utc_now()
        record.lifecycle_status = FoodLifecycle.DELETED.value
        record.deleted_at = deleted_at
        record.updated_at = deleted_at
        await self._session.flush()
        return True
