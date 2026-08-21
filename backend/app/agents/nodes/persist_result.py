"""Optional persistence boundary kept out of pure analysis nodes."""

from app.agents.state import AnalysisDependencies, AnalysisState


async def persist_result(
    state: AnalysisState, dependencies: AnalysisDependencies
) -> dict[str, object]:
    if dependencies.persist is not None:
        await dependencies.persist(state)
    return {}

