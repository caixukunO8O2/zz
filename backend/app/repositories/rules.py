"""Preservation-rule lookup operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import PreservationRuleModel


def _normalize(value: str) -> str:
    return "".join(value.split())


class RuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_name(self, name: str) -> PreservationRuleModel | None:
        normalized = _normalize(name)
        if not normalized:
            return None
        rules = await self._session.scalars(
            select(PreservationRuleModel).where(PreservationRuleModel.enabled.is_(True))
        )
        for rule in rules:
            if normalized == _normalize(rule.food_name) or any(
                normalized == _normalize(alias) for alias in rule.aliases
            ):
                return rule
        return None
