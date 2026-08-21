from io import BytesIO

from PIL import Image, ImageDraw

from app.services.image_quality import assess_image, hamming_distance


def _jpeg_bytes(*, dark: bool = False) -> bytes:
    image = Image.new("RGB", (640, 640), (5, 5, 5) if dark else (245, 245, 245))
    if not dark:
        draw = ImageDraw.Draw(image)
        for offset in range(0, 640, 32):
            draw.rectangle(
                (offset, 0, min(offset + 15, 639), 639), fill=(20, 20, 20)
            )
        draw.text((180, 280), "2026-08-25", fill=(220, 40, 40))
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def test_dark_image_is_rejected() -> None:
    result = assess_image(_jpeg_bytes(dark=True))

    assert result.accepted is False
    assert result.reason == "image_too_dark"


def test_clear_image_has_content_and_perceptual_hashes() -> None:
    result = assess_image(_jpeg_bytes())

    assert result.accepted is True
    assert len(result.sha256) == 64
    assert len(result.perceptual_hash) == 16
    assert result.width == result.height == 640


def test_hamming_distance_counts_changed_bits() -> None:
    assert hamming_distance("0000000000000000", "000000000000000f") == 4

