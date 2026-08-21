"""Decide whether OCR evidence still needs visual food identification."""

from app.agents.state import AnalysisState


def decide_visual(state: AnalysisState) -> dict[str, object]:
    fields = state["fields"]
    required = (
        fields.food_name is None
        or fields.food_name.confidence < 0.70
        or fields.category is None
    )
    return {"visual_required": required}

