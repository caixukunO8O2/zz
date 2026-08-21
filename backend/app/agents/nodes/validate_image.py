"""Validate the graph's required image inputs."""

from app.agents.state import AnalysisState


def validate_image(state: AnalysisState) -> dict[str, object]:
    if "image" not in state or "purpose" not in state:
        raise ValueError("analysis image and purpose are required")
    images = state.get("images") or [state["image"]]
    return {"images": images}

