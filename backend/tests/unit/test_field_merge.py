from datetime import date

from app.domain.scans import (
    DetectedField,
    FieldCandidate,
    FieldSource,
    ScanFields,
    merge_fields,
)


def _field(value, confidence: float, source: FieldSource, evidence: str):
    return DetectedField(
        value=value,
        confidence=confidence,
        source_image_id=1,
        source_kind=source,
        evidence_text=evidence,
    )


def test_lower_confidence_vision_does_not_replace_ocr_name() -> None:
    existing = _field("伊利鲜牛奶", 0.88, FieldSource.OCR, "鲜牛奶")
    candidate = _field("纯牛奶", 0.65, FieldSource.VISION, "包装正面")

    merged = merge_fields(
        ScanFields(food_name=existing),
        [FieldCandidate("food_name", candidate)],
    )

    assert merged.fields.food_name == existing
    assert merged.conflicts == ()


def test_user_confirmed_value_cannot_be_replaced_by_ocr() -> None:
    existing = _field("草莓", 1.0, FieldSource.USER, "用户确认")
    candidate = _field("树莓", 0.99, FieldSource.OCR, "树莓")

    merged = merge_fields(
        ScanFields(food_name=existing),
        [FieldCandidate("food_name", candidate)],
    )

    assert merged.fields.food_name == existing


def test_equal_confidence_from_same_source_keeps_existing_value() -> None:
    existing = _field("伊利", 0.8, FieldSource.OCR, "伊利")
    candidate = _field("蒙牛", 0.8, FieldSource.OCR, "蒙牛")

    merged = merge_fields(
        ScanFields(brand=existing),
        [FieldCandidate("brand", candidate)],
    )

    assert merged.fields.brand == existing


def test_declared_expiry_conflict_keeps_both_evidence_items() -> None:
    existing = _field(
        date(2026, 8, 25), 0.91, FieldSource.OCR, "有效期至 2026-08-25"
    )
    candidate = _field(
        date(2026, 8, 28), 0.95, FieldSource.OCR, "EXP 2026-08-28"
    )

    merged = merge_fields(
        ScanFields(declared_expiry_date=existing),
        [FieldCandidate("declared_expiry_date", candidate)],
    )

    assert merged.fields.declared_expiry_date == existing
    assert len(merged.conflicts) == 1
    assert merged.conflicts[0].existing == existing
    assert merged.conflicts[0].candidate == candidate
