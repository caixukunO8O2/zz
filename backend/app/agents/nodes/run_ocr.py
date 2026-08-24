"""Run OCR and normalize labelled date evidence."""

from app.agents.state import AnalysisDependencies, AnalysisState
from app.domain.date_parser import parse_date_candidates
from app.domain.scans import DetectedField, FieldCandidate, FieldSource


async def run_ocr(
    state: AnalysisState, dependencies: AnalysisDependencies
) -> dict[str, object]:
    result = await dependencies.ocr.extract(state["image"], state["purpose"])
    candidates = [
        FieldCandidate(field_name, field)
        for field_name, field in result.fields.items()
    ]
    existing_names = set(result.fields)
    for parsed in parse_date_candidates(result.text, state["added_on"]):
        if not parsed.auto_confirm or parsed.field_name in existing_names:
            continue
        candidates.append(
            FieldCandidate(
                parsed.field_name,
                DetectedField(
                    value=parsed.value,
                    confidence=0.9,
                    source_image_id=state["image"].source_image_id,
                    source_kind=FieldSource.OCR,
                    evidence_text=parsed.evidence_text,
                ),
            )
        )
    return {"ocr_text": result.text, "pending_candidates": candidates}

