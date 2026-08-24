"""Merge one provider's pending candidates into accumulated scan fields."""

from app.agents.state import AnalysisState
from app.domain.scans import ScanFields, merge_fields


def merge_pending_fields(state: AnalysisState) -> dict[str, object]:
    result = merge_fields(
        state.get("fields", ScanFields()), state.get("pending_candidates", [])
    )
    return {
        "fields": result.fields,
        "conflicts": state.get("conflicts", ()) + result.conflicts,
        "pending_candidates": [],
    }

