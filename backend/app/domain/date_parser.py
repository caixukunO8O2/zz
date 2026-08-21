"""Conservative parsing of labelled package date evidence."""

import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ParsedDateCandidate:
    field_name: str
    value: date
    evidence_text: str
    auto_confirm: bool


_FOUR_DIGIT_DATE = re.compile(
    r"(?P<year>\d{4})\s*(?:年|[./-])\s*(?P<month>\d{1,2})"
    r"\s*(?:月|[./-])\s*(?P<day>\d{1,2})\s*日?"
)
_TWO_DIGIT_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})(?!\d)"
)
_MONTH_DAY = re.compile(r"(?<!\d)(?P<month>\d{1,2})[./-](?P<day>\d{1,2})(?!\d)")


def _field_name(text: str, start: int) -> str:
    prefix = text[max(0, start - 16) : start].upper()
    if "生产" in prefix or "MFG" in prefix:
        return "production_date"
    if any(label in prefix for label in ("有效", "EXP", "到期")):
        return "declared_expiry_date"
    return "unknown_date"


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_candidates(
    text: str, reference_date: date
) -> tuple[ParsedDateCandidate, ...]:
    candidates: list[ParsedDateCandidate] = []
    occupied: list[tuple[int, int]] = []
    for match in _FOUR_DIGIT_DATE.finditer(text):
        value = _safe_date(
            int(match["year"]), int(match["month"]), int(match["day"])
        )
        if value is None:
            continue
        field_name = _field_name(text, match.start())
        candidates.append(
            ParsedDateCandidate(
                field_name=field_name,
                value=value,
                evidence_text=match.group(0),
                auto_confirm=field_name != "unknown_date",
            )
        )
        occupied.append(match.span())
    for match in _TWO_DIGIT_DATE.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        value = _safe_date(
            2000 + int(match["year"]),
            int(match["month"]),
            int(match["day"]),
        )
        if value is not None:
            candidates.append(
                ParsedDateCandidate(
                    field_name=_field_name(text, match.start()),
                    value=value,
                    evidence_text=match.group(0),
                    auto_confirm=False,
                )
            )
            occupied.append(match.span())
    for match in _MONTH_DAY.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        value = _safe_date(
            reference_date.year, int(match["month"]), int(match["day"])
        )
        if value is not None:
            candidates.append(
                ParsedDateCandidate(
                    field_name=_field_name(text, match.start()),
                    value=value,
                    evidence_text=match.group(0),
                    auto_confirm=False,
                )
            )
    return tuple(candidates)

