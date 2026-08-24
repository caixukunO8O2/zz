"""Analysis adapter selection without provider-specific service coupling."""

from dataclasses import dataclass

from app.adapters.bailian_client import BailianClient
from app.adapters.bailian_ocr import BailianOcrAdapter
from app.adapters.bailian_vision import BailianVisionAdapter
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
    *,
    mock_scenario: str | None,
    frame_index: int,
    analysis_provider: str | None = None,
    app_mode: str | None = None,
    dashscope_api_key: str = "",
    bailian_base_url: str = "",
    bailian_ocr_model: str = "qwen3.5-ocr",
    bailian_vision_model: str = "qwen3.7-flash",
) -> AnalysisAdapters:
    provider = analysis_provider or app_mode or "mock"
    if provider == "bailian":
        if not dashscope_api_key or not bailian_base_url:
            raise APIError(
                503, "analysis_provider_unavailable", "识别服务暂时不可用", True
            )
        client = BailianClient(
            dashscope_api_key, bailian_base_url, timeout_seconds=12
        )
        return AnalysisAdapters(
            ocr=BailianOcrAdapter(client, bailian_ocr_model),
            vision=BailianVisionAdapter(client, bailian_vision_model),
        )
    if provider != "mock":
        raise APIError(
            503, "analysis_provider_unavailable", "识别服务暂时不可用", True
        )
    scenario = mock_scenario or "packaged_success"
    return AnalysisAdapters(
        ocr=MockOcrAdapter(scenario, frame_index),
        vision=MockVisionAdapter(scenario, frame_index),
    )
