"""Small DashScope multimodal HTTP client shared by real analysis adapters."""

import asyncio
import base64
from typing import Protocol, runtime_checkable

import httpx

from app.ports.storage import StoredImage


class BailianProviderError(RuntimeError):
    """Provider-neutral failure safe to retry without exposing response details."""


@runtime_checkable
class BailianClientPort(Protocol):
    async def generate(
        self,
        *,
        model: str,
        images: list[StoredImage],
        prompt: str | None = None,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]: ...


class BailianClient:
    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 20) -> None:
        if not api_key.strip():
            raise ValueError("DashScope API key is required")
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout_seconds

    @staticmethod
    async def _image_content(image: StoredImage) -> dict[str, object]:
        raw = await asyncio.to_thread(image.path.read_bytes)
        encoded = base64.b64encode(raw).decode("ascii")
        return {
            "image": f"data:{image.content_type};base64,{encoded}",
            "min_pixels": 65_536,
            "max_pixels": 8_388_608,
            "enable_rotate": True,
        }

    async def generate(
        self,
        *,
        model: str,
        images: list[StoredImage],
        prompt: str | None = None,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if not images:
            raise BailianProviderError("analysis image is required")
        content: list[dict[str, object]] = [
            await self._image_content(image) for image in images
        ]
        if prompt:
            content.append({"text": prompt})
        payload: dict[str, object] = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
        }
        if parameters:
            payload["parameters"] = parameters
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BailianProviderError("Bailian analysis request failed") from exc
        if not isinstance(body, dict):
            raise BailianProviderError("Bailian analysis response was invalid")
        return body


def first_content(payload: dict[str, object]) -> dict[str, object]:
    """Read the first native multimodal content item with strict shape checks."""
    try:
        output = payload["output"]
        choices = output["choices"]  # type: ignore[index]
        message = choices[0]["message"]
        content = message["content"]
        item = content[0]
    except (KeyError, IndexError, TypeError) as exc:
        raise BailianProviderError("Bailian analysis response was invalid") from exc
    if not isinstance(item, dict):
        raise BailianProviderError("Bailian analysis response was invalid")
    return item
