"""Analysis adapter selection without provider-specific service coupling."""

from dataclasses import dataclass

from app.adapters.mock_ocr import MockOcrAdapter
from app.adapters.mock_vision import MockVisionAdapter
from app.core.errors import APIError
from app.ports.ocr import OcrPort
from app.ports.vision import VisionPort


@dataclass(frozen=True, slots=True)
class AnalysisAdapters:
    ocr: OcrPort
    vision: VisionPort


def create_analysis_adapters(
    *, app_mode: str, mock_scenario: str | None, frame_index: int
) -> AnalysisAdapters:
    if app_mode != "mock":
        raise APIError(
            503, "analysis_provider_unavailable", "识别服务暂时不可用", True
        )
    scenario = mock_scenario or "packaged_success"
    return AnalysisAdapters(
        ocr=MockOcrAdapter(scenario, frame_index),
        vision=MockVisionAdapter(scenario, frame_index),
    )

