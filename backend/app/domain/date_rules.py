"""Pure rules for selecting food consume-by dates and freshness buckets."""

from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.foods import DateBasis, FreshnessBucket


class DateRuleError(ValueError):
    """Base class for invalid or insufficient food date information."""


class InvalidShelfLifeError(DateRuleError):
    """Raised when a shelf life is less than zero days."""


class InvalidDateOrderError(DateRuleError):
    """Raised when declared expiry precedes the production date."""


class MissingDateBasisError(DateRuleError):
    """Raised when no supported basis can determine a consume-by date."""


@dataclass(frozen=True, slots=True)
class DateCalculation:
    """The consume-by date and the basis used to determine it."""

    consume_by: date
    basis: DateBasis
    conflict: bool


def calculate_consume_by(
    declared_expiry: date | None,
    production_date: date | None,
    shelf_life_days: int | None,
    added_on: date,
    knowledge_days: int | None,
    *,
    manual_consume_by: date | None = None,
) -> DateCalculation:
    """Determine a consume-by date using the most specific available evidence."""
    if shelf_life_days is not None and shelf_life_days < 0:
        raise InvalidShelfLifeError("shelf-life days must not be negative")
    if (
        declared_expiry is not None
        and production_date is not None
        and declared_expiry < production_date
    ):
        raise InvalidDateOrderError(
            "declared expiry must not be earlier than production date"
        )

    calculated = (
        production_date + timedelta(days=shelf_life_days)
        if production_date is not None and shelf_life_days is not None
        else None
    )
    if declared_expiry is not None:
        return DateCalculation(
            declared_expiry,
            DateBasis.DECLARED_EXPIRY,
            calculated is not None and calculated != declared_expiry,
        )
    if calculated is not None:
        return DateCalculation(calculated, DateBasis.PRODUCTION_PLUS_SHELF_LIFE, False)
    if knowledge_days is not None:
        return DateCalculation(
            added_on + timedelta(days=knowledge_days),
            DateBasis.KNOWLEDGE_BASE_ESTIMATE,
            False,
        )
    if manual_consume_by is not None:
        return DateCalculation(
            manual_consume_by,
            DateBasis.MANUAL_USER_SET,
            False,
        )
    raise MissingDateBasisError("manual consume-by date is required")


def freshness_bucket(consume_by: date, today: date) -> FreshnessBucket:
    """Group a food by calendar days remaining until its consume-by date."""
    remaining_days = (consume_by - today).days
    if remaining_days < 0:
        return FreshnessBucket.EXPIRED
    if remaining_days <= 1:
        return FreshnessBucket.URGENT
    if remaining_days <= 7:
        return FreshnessBucket.THIS_WEEK
    return FreshnessBucket.NORMAL
