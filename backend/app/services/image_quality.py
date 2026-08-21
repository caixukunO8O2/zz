"""Deterministic image validation and duplicate-detection features."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from statistics import fmean
from typing import cast

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIN_IMAGE_SIDE = 480
MIN_BRIGHTNESS = 35.0
MAX_BRIGHTNESS = 248.0
MIN_SHARPNESS = 3.0


@dataclass(frozen=True, slots=True)
class ImageAssessment:
    width: int
    height: int
    brightness: float
    sharpness: float
    sha256: str
    perceptual_hash: str
    accepted: bool
    reason: str | None
    image_format: str | None


def _rejected(content: bytes, reason: str) -> ImageAssessment:
    return ImageAssessment(
        width=0,
        height=0,
        brightness=0,
        sharpness=0,
        sha256=sha256(content).hexdigest(),
        perceptual_hash="0" * 16,
        accepted=False,
        reason=reason,
        image_format=None,
    )


def _average_hash(image: Image.Image) -> str:
    pixels = cast(
        tuple[int, ...],
        image.resize((8, 8)).convert("L").get_flattened_data(),
    )
    mean = fmean(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | int(value >= mean)
    return f"{bits:016x}"


def _sharpness(image: Image.Image) -> float:
    thumbnail = image.resize((64, 64)).convert("L")
    pixels = cast(tuple[int, ...], thumbnail.get_flattened_data())
    differences: list[int] = []
    for y in range(64):
        row = y * 64
        differences.extend(
            abs(pixels[row + x] - pixels[row + x + 1]) for x in range(63)
        )
    for y in range(63):
        row = y * 64
        next_row = row + 64
        differences.extend(
            abs(pixels[row + x] - pixels[next_row + x]) for x in range(64)
        )
    return fmean(differences)


def assess_image(content: bytes) -> ImageAssessment:
    if len(content) > MAX_IMAGE_BYTES:
        return _rejected(content, "image_too_large")
    try:
        with Image.open(BytesIO(content)) as opened:
            image_format = opened.format
            if image_format not in {"JPEG", "PNG"}:
                return _rejected(content, "unsupported_image_type")
            opened.load()
            image = opened.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return _rejected(content, "invalid_image")

    width, height = image.size
    grayscale = image.resize((64, 64)).convert("L")
    brightness = fmean(
        cast(tuple[int, ...], grayscale.get_flattened_data())
    )
    sharpness = _sharpness(image)
    reason: str | None = None
    if width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE:
        reason = "image_too_small"
    elif brightness < MIN_BRIGHTNESS:
        reason = "image_too_dark"
    elif brightness > MAX_BRIGHTNESS:
        reason = "image_overexposed"
    elif sharpness < MIN_SHARPNESS:
        reason = "image_too_blurry"
    return ImageAssessment(
        width=width,
        height=height,
        brightness=brightness,
        sharpness=sharpness,
        sha256=sha256(content).hexdigest(),
        perceptual_hash=_average_hash(image),
        accepted=reason is None,
        reason=reason,
        image_format=image_format,
    )


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()
