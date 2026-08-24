"""Versioned preservation estimates and their CSV seed loader."""

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.domain.foods import StorageType

CSV_COLUMNS = (
    "name",
    "aliases",
    "category",
    "room_days",
    "chilled_days",
    "frozen_days",
    "source_note",
    "version",
)
EXPECTED_CATEGORY_COUNTS = {
    "fruit": 20,
    "vegetable": 20,
    "meat": 10,
    "dairy": 10,
    "cooked": 10,
}


@dataclass(frozen=True, slots=True)
class PreservationRule:
    """Estimated storage durations for one food and one seed version."""

    name: str
    aliases: tuple[str, ...]
    category: str
    room_days: int | None
    chilled_days: int | None
    frozen_days: int | None
    source_note: str
    version: str

    def days_for(self, storage_type: StorageType) -> int | None:
        """Return the estimate for a storage type, or ``None`` if unsupported."""
        if storage_type is StorageType.ROOM:
            return self.room_days
        if storage_type is StorageType.CHILLED:
            return self.chilled_days
        if storage_type is StorageType.FROZEN:
            return self.frozen_days
        raise ValueError(f"unsupported storage type: {storage_type!r}")


def _normalize(value: str) -> str:
    """Normalize names by removing surrounding and internal Unicode whitespace."""
    return "".join(value.split())


def _parse_days(value: str, row_number: int, column: str) -> int | None:
    if not value.strip():
        return None
    try:
        days = int(value)
    except ValueError as exc:
        raise ValueError(f"invalid {column} on row {row_number}: {value!r}") from exc
    if days < 0:
        raise ValueError(f"negative {column} on row {row_number}")
    return days


def load_seed_rules(path: Path) -> tuple[PreservationRule, ...]:
    """Load and validate the versioned preservation rules in ``path``."""
    with path.open("r", encoding="utf-8-sig", newline="") as seed_file:
        reader = csv.DictReader(seed_file)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValueError(f"CSV columns must be exactly {CSV_COLUMNS!r}")

        rules: list[PreservationRule] = []
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            if row.get(None) is not None:
                raise ValueError(f"unexpected columns on row {row_number}")

            raw_name = row["name"] or ""
            name = raw_name.strip()
            normalized_name = _normalize(name)
            if not normalized_name:
                raise ValueError(f"missing name on row {row_number}")

            category = (row["category"] or "").strip()
            if not category:
                raise ValueError(f"missing category on row {row_number}")
            if category not in EXPECTED_CATEGORY_COUNTS:
                raise ValueError(f"unknown category on row {row_number}: {category!r}")

            if normalized_name in seen:
                raise ValueError(f"duplicate normalized name or alias on row {row_number}")
            seen.add(normalized_name)

            raw_aliases = (row["aliases"] or "").strip()
            aliases: list[str] = []
            if raw_aliases:
                for raw_alias in raw_aliases.split("|"):
                    alias = raw_alias.strip()
                    normalized_alias = _normalize(alias)
                    if not normalized_alias:
                        raise ValueError(f"missing alias on row {row_number}")
                    if normalized_alias in seen:
                        raise ValueError(f"duplicate normalized name or alias on row {row_number}")
                    seen.add(normalized_alias)
                    aliases.append(alias)

            rules.append(
                PreservationRule(
                    name=name,
                    aliases=tuple(aliases),
                    category=category,
                    room_days=_parse_days(row["room_days"] or "", row_number, "room_days"),
                    chilled_days=_parse_days(row["chilled_days"] or "", row_number, "chilled_days"),
                    frozen_days=_parse_days(row["frozen_days"] or "", row_number, "frozen_days"),
                    source_note=(row["source_note"] or "").strip(),
                    version=(row["version"] or "").strip(),
                )
            )

    counts = Counter(rule.category for rule in rules)
    if counts != EXPECTED_CATEGORY_COUNTS:
        raise ValueError(
            f"category counts must be {EXPECTED_CATEGORY_COUNTS!r}, got {dict(counts)!r}"
        )
    return tuple(rules)


def find_rule(
    rules: tuple[PreservationRule, ...] | list[PreservationRule], food_name: str
) -> PreservationRule | None:
    """Find a rule by normalized exact name or alias, without fuzzy matching."""
    normalized_query = _normalize(food_name)
    if not normalized_query:
        return None
    for rule in rules:
        if normalized_query == _normalize(rule.name):
            return rule
        if any(normalized_query == _normalize(alias) for alias in rule.aliases):
            return rule
    return None
