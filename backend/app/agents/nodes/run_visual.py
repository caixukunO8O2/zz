"""Run visual identity only when the graph determines it is needed."""

from app.agents.state import AnalysisDependencies, AnalysisState
from app.domain.scans import FieldCandidate


async def run_visual(
    state: AnalysisState, dependencies: AnalysisDependencies
) -> dict[str, object]:
    result = await dependencies.vision.identify(
        state["images"], state.get("ocr_text", "")
    )
    return {
        "pending_candidates": [
            FieldCandidate(field_name, field)
            for field_name, field in result.fields.items()
        ]
    }

