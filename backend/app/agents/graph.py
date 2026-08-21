"""Build the dependency-injected LangGraph scan analysis workflow."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.nodes.calculate_date import calculate_date
from app.agents.nodes.decide_guidance import decide_guidance
from app.agents.nodes.decide_visual import decide_visual
from app.agents.nodes.merge_fields import merge_pending_fields
from app.agents.nodes.persist_result import persist_result
from app.agents.nodes.run_ocr import run_ocr
from app.agents.nodes.run_visual import run_visual
from app.agents.nodes.validate_image import validate_image
from app.agents.state import AnalysisDependencies, AnalysisState

__all__ = ["AnalysisDependencies", "build_analysis_graph"]


def _visual_route(state: AnalysisState) -> str:
    return "run_visual" if state.get("visual_required") else "calculate_date"


def build_analysis_graph(
    dependencies: AnalysisDependencies,
) -> CompiledStateGraph:
    async def ocr_node(state: AnalysisState) -> dict[str, object]:
        return await run_ocr(state, dependencies)

    async def visual_node(state: AnalysisState) -> dict[str, object]:
        return await run_visual(state, dependencies)

    async def date_node(state: AnalysisState) -> dict[str, object]:
        return await calculate_date(state, dependencies)

    async def persist_node(state: AnalysisState) -> dict[str, object]:
        return await persist_result(state, dependencies)

    builder = StateGraph(AnalysisState)
    builder.add_node("validate_image", validate_image)
    builder.add_node("run_ocr", ocr_node)
    builder.add_node("merge_ocr", merge_pending_fields)
    builder.add_node("decide_visual", decide_visual)
    builder.add_node("run_visual", visual_node)
    builder.add_node("merge_visual", merge_pending_fields)
    builder.add_node("calculate_date", date_node)
    builder.add_node("decide_guidance", decide_guidance)
    builder.add_node("persist_result", persist_node)

    builder.add_edge(START, "validate_image")
    builder.add_edge("validate_image", "run_ocr")
    builder.add_edge("run_ocr", "merge_ocr")
    builder.add_edge("merge_ocr", "decide_visual")
    builder.add_conditional_edges(
        "decide_visual",
        _visual_route,
        {
            "run_visual": "run_visual",
            "calculate_date": "calculate_date",
        },
    )
    builder.add_edge("run_visual", "merge_visual")
    builder.add_edge("merge_visual", "calculate_date")
    builder.add_edge("calculate_date", "decide_guidance")
    builder.add_edge("decide_guidance", "persist_result")
    builder.add_edge("persist_result", END)
    return builder.compile()

