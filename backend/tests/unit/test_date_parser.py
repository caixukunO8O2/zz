from datetime import date

import pytest

from app.domain.date_parser import parse_date_candidates


@pytest.mark.parametrize(
    ("text", "expected", "field_name"),
    [
        ("生产日期 2026.08.18", date(2026, 8, 18), "production_date"),
        ("有效期至 2026/08/25", date(2026, 8, 25), "declared_expiry_date"),
        ("EXP 2026-08-25", date(2026, 8, 25), "declared_expiry_date"),
        ("生产日期 2026年08月18日", date(2026, 8, 18), "production_date"),
    ],
)
def test_date_parser_accepts_supported_separators(
    text: str, expected: date, field_name: str
) -> None:
    candidate = parse_date_candidates(text, date(2026, 8, 20))[0]

    assert candidate.value == expected
    assert candidate.field_name == field_name
    assert candidate.auto_confirm is True


@pytest.mark.parametrize(
    "text", ["有效期 26/08/25", "有效期 08/25", "有效期见包装顶部"]
)
def test_ambiguous_or_non_date_text_is_not_auto_confirmed(text: str) -> None:
    assert all(
        candidate.auto_confirm is False
        for candidate in parse_date_candidates(text, date(2026, 8, 20))
    )


def test_invalid_calendar_date_is_rejected() -> None:
    assert parse_date_candidates("有效期至 2026-02-30", date(2026, 8, 20)) == ()

