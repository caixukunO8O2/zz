from datetime import date
from pathlib import Path

import pytest

from app.adapters.bailian_client import BailianClient
from app.adapters.bailian_ocr import BailianOcrAdapter
from app.adapters.bailian_vision import BailianVisionAdapter
from app.adapters.factory import create_analysis_adapters
from app.domain.foods import StorageType
from app.domain.scans import ImagePurpose
from app.ports.storage import StoredImage


class FakeBailianClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        model: str,
        images: list[StoredImage],
        prompt: str | None = None,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "model": model,
                "images": images,
                "prompt": prompt,
                "parameters": parameters,
            }
        )
        return self.responses.pop(0)


def stored_image(image_id: int = 7) -> StoredImage:
    return StoredImage(Path("D:/uploads/food.jpg"), "image/jpeg", image_id)


@pytest.mark.asyncio
async def test_bailian_image_payload_meets_qwen_flash_pixel_floor(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "food.jpg"
    image_path.write_bytes(b"image-bytes")

    content = await BailianClient._image_content(
        StoredImage(image_path, "image/jpeg", 1)
    )

    assert content["min_pixels"] == 65_536


def test_factory_selects_real_bailian_adapters_independently_of_app_mode() -> None:
    adapters = create_analysis_adapters(
        analysis_provider="bailian",
        mock_scenario=None,
        frame_index=1,
        dashscope_api_key="test-key",
        bailian_base_url="https://example.invalid/generation",
        bailian_ocr_model="qwen3.5-ocr",
        bailian_vision_model="qwen3.7-flash",
    )

    assert isinstance(adapters.ocr, BailianOcrAdapter)
    assert isinstance(adapters.vision, BailianVisionAdapter)


@pytest.mark.asyncio
async def test_qwen_ocr_maps_packaging_fields_to_typed_candidates() -> None:
    client = FakeBailianClient(
        [
            {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "ocr_result": {
                                            "kv_result": {
                                                "商品名称": "伊利鲜牛奶",
                                                "品牌": "伊利",
                                                "食材分类": "dairy",
                                                "生产日期": "2026-08-18",
                                                "过期日期": None,
                                                "保质期天数": "7",
                                                "储存条件": "冷藏",
                                            }
                                        },
                                        "text": "伊利鲜牛奶 生产日期2026-08-18 保质期7天 冷藏",
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        ]
    )

    result = await BailianOcrAdapter(client, "qwen3.5-ocr").extract(
        stored_image(), ImagePurpose.GENERAL
    )

    assert client.calls[0]["model"] == "qwen3.5-ocr"
    assert result.text == "伊利鲜牛奶 生产日期2026-08-18 保质期7天 冷藏"
    assert result.fields["food_name"].value == "伊利鲜牛奶"
    assert result.fields["production_date"].value == date(2026, 8, 18)
    assert result.fields["shelf_life_days"].value == 7
    assert result.fields["storage_type"].value is StorageType.CHILLED
    assert "declared_expiry_date" not in result.fields


@pytest.mark.asyncio
async def test_qwen_flash_returns_only_supported_visual_identity_fields() -> None:
    client = FakeBailianClient(
        [
            {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "text": (
                                            '{"food_name":"草莓","brand":null,'
                                            '"category":"fruit","confidence":0.96}'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        ]
    )

    result = await BailianVisionAdapter(client, "qwen3.7-flash").identify(
        [stored_image()], ""
    )

    assert client.calls[0]["model"] == "qwen3.7-flash"
    assert result.fields["food_name"].value == "草莓"
    assert result.fields["category"].value == "fruit"
    assert "brand" not in result.fields


@pytest.mark.asyncio
async def test_qwen_flash_rejects_an_unknown_food_category() -> None:
    client = FakeBailianClient(
        [
            {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "text": (
                                            '{"food_name":"矿泉水","brand":null,'
                                            '"category":"drink","confidence":0.91}'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        ]
    )

    result = await BailianVisionAdapter(client, "qwen3.7-flash").identify(
        [stored_image()], ""
    )

    assert result.fields["food_name"].value == "矿泉水"
    assert "category" not in result.fields
