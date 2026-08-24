from dataclasses import FrozenInstanceError
from datetime import date, timedelta

import pytest

from app.domain.date_rules import (
    MAX_SHELF_LIFE_DAYS,
    InvalidDateOrderError,
    InvalidDateRangeError,
    InvalidShelfLifeError,
    MissingDateBasisError,
    calculate_consume_by,
    freshness_bucket,
)
from app.domain.foods import DateBasis


def test_declared_expiry_has_priority() -> None:
    result = calculate_consume_by(
        declared_expiry=date(2026, 8, 24),
        production_date=date(2026, 8, 18),
        shelf_life_days=7,
        added_on=date(2026, 8, 20),
        knowledge_days=5,
    )

    assert result.consume_by == date(2026, 8, 24)
    assert result.basis is DateBasis.DECLARED_EXPIRY
    assert result.conflict is True


def test_production_plus_shelf_life_adds_n_calendar_days() -> None:
    result = calculate_consume_by(
        None,
        date(2026, 8, 18),
        7,
        date(2026, 8, 20),
        None,
    )

    assert result.consume_by == date(2026, 8, 25)
    assert result.basis is DateBasis.PRODUCTION_PLUS_SHELF_LIFE


def test_knowledge_estimate_uses_added_date_when_no_more_specific_basis_exists() -> None:
    result = calculate_consume_by(None, None, None, date(2026, 8, 20), 5)

    assert result.consume_by == date(2026, 8, 25)
    assert result.basis is DateBasis.KNOWLEDGE_BASE_ESTIMATE
    assert result.conflict is False


def test_manual_user_date_is_the_final_fallback() -> None:
    result = calculate_consume_by(
        None,
        None,
        None,
        date(2026, 8, 20),
        None,
        manual_consume_by=date(2026, 8, 30),
    )

    assert result.consume_by == date(2026, 8, 30)
    assert result.basis is DateBasis.MANUAL_USER_SET
    assert result.conflict is False


def test_specific_date_basis_wins_over_manual_fallback() -> None:
    result = calculate_consume_by(
        date(2026, 8, 24),
        date(2026, 8, 18),
        7,
        date(2026, 8, 20),
        5,
        manual_consume_by=date(2026, 9, 1),
    )

    assert result.consume_by == date(2026, 8, 24)
    assert result.basis is DateBasis.DECLARED_EXPIRY


def test_negative_shelf_life_is_rejected() -> None:
    with pytest.raises(InvalidShelfLifeError):
        calculate_consume_by(None, date(2026, 8, 18), -1, date(2026, 8, 20), None)


def test_shelf_life_has_safe_upper_bound_and_date_overflow_is_typed() -> None:
    result = calculate_consume_by(
        None,
        date(2026, 8, 18),
        MAX_SHELF_LIFE_DAYS,
        date(2026, 8, 20),
        None,
    )
    assert result.consume_by == date(2126, 7, 25)

    with pytest.raises(InvalidShelfLifeError):
        calculate_consume_by(
            None,
            date(2026, 8, 18),
            MAX_SHELF_LIFE_DAYS + 1,
            date(2026, 8, 20),
            None,
        )
    with pytest.raises(InvalidDateRangeError):
        calculate_consume_by(
            None,
            date(9999, 12, 31),
            1,
            date(9999, 12, 31),
            None,
        )


def test_declared_expiry_before_production_date_is_rejected() -> None:
    with pytest.raises(InvalidDateOrderError):
        calculate_consume_by(
            date(2026, 8, 17),
            date(2026, 8, 18),
            None,
            date(2026, 8, 20),
            None,
        )


def test_missing_date_basis_requires_manual_consume_by_date() -> None:
    with pytest.raises(MissingDateBasisError, match="manual consume-by date is required"):
        calculate_consume_by(None, None, None, date(2026, 8, 20), None)


def test_date_calculation_is_immutable() -> None:
    result = calculate_consume_by(None, None, None, date(2026, 8, 20), 5)

    with pytest.raises(FrozenInstanceError):
        result.consume_by = date(2026, 8, 26)


@pytest.mark.parametrize(
    ("remaining", "bucket"),
    [
        (-1, "expired"),
        (0, "urgent"),
        (1, "urgent"),
        (2, "this_week"),
        (7, "this_week"),
        (8, "normal"),
    ],
)
def test_freshness_boundaries(remaining: int, bucket: str) -> None:
    assert (
        freshness_bucket(
            date(2026, 8, 20) + timedelta(days=remaining),
            date(2026, 8, 20),
        ).value
        == bucket
    )
