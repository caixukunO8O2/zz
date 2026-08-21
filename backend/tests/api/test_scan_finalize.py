from datetime import date
from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.foods import StorageType
from app.domain.scans import (
    DetectedField,
    FieldConflict,
    FieldSource,
    ScanFields,
    conflicts_to_json,
    scan_fields_to_json,
)
from app.models.scan_entities import ScanSession


async def _analyzed_scan(
    client: AsyncClient,
    headers: dict[str, str],
    image: bytes,
    *,
    scenario: str = "packaged_success",
) -> dict[str, object]:
    created = await client.post(
        "/api/v1/scan-sessions",
        json={"mock_scenario": scenario},
        headers=headers,
    )
    assert created.status_code == 201
    scan_id = created.json()["id"]
    uploaded = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": ("scan.jpg", image, "image/jpeg")},
        data={"purpose": "general"},
        headers={**headers, "Idempotency-Key": f"upload-{scan_id}"},
    )
    assert uploaded.status_code == 202
    current = await client.get(f"/api/v1/scan-sessions/{scan_id}", headers=headers)
    assert current.status_code == 200
    return dict(current.json())


@pytest.mark.asyncio
async def test_duplicate_finalize_returns_same_food(
    scan_client: AsyncClient, scan_auth_headers, scan_image_bytes
) -> None:
    headers = await scan_auth_headers()
    scan = await _analyzed_scan(scan_client, headers, scan_image_bytes())
    request_headers = {**headers, "Idempotency-Key": "finalize-1"}

    first = await scan_client.post(
        f"/api/v1/scan-sessions/{scan['id']}/finalize",
        json={},
        headers=request_headers,
    )
    replay = await scan_client.post(
        f"/api/v1/scan-sessions/{scan['id']}/finalize",
        json={},
        headers=request_headers,
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json()["food"]["id"] == replay.json()["food"]["id"]


@pytest.mark.asyncio
async def test_finalize_requires_explicit_conflict_choice(
    scan_client: AsyncClient,
    scan_auth_headers,
    scan_image_bytes,
    scan_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await scan_auth_headers("conflict-owner")
    scan = await _analyzed_scan(scan_client, headers, scan_image_bytes())
    existing = DetectedField(
        value=date(2026, 8, 25),
        confidence=0.91,
        source_image_id=scan["images"][0]["id"],
        source_kind=FieldSource.OCR,
        evidence_text="有效期至 2026-08-25",
    )
    candidate = DetectedField(
        value=date(2026, 8, 28),
        confidence=0.95,
        source_image_id=scan["images"][0]["id"],
        source_kind=FieldSource.OCR,
        evidence_text="EXP 2026-08-28",
    )
    async with scan_session_factory() as session:
        record = await session.get(ScanSession, scan["id"])
        assert record is not None
        record.detected_fields = scan_fields_to_json(
            ScanFields(
                food_name=DetectedField(
                    "伊利鲜牛奶", 0.9, None, FieldSource.OCR, "伊利鲜牛奶"
                ),
                category=DetectedField(
                    "dairy", 0.9, None, FieldSource.OCR, "鲜牛奶"
                ),
                declared_expiry_date=existing,
                storage_type=DetectedField(
                    StorageType.CHILLED,
                    0.9,
                    None,
                    FieldSource.OCR,
                    "冷藏",
                ),
            )
        )
        record.conflicts = conflicts_to_json(
            (FieldConflict("declared_expiry_date", existing, candidate),)
        )
        record.status = "needs_input"
        await session.commit()

    response = await scan_client.post(
        f"/api/v1/scan-sessions/{scan['id']}/finalize",
        json={},
        headers={**headers, "Idempotency-Key": "finalize-conflict"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "date_conflict_requires_choice"


@pytest.mark.asyncio
async def test_finalize_same_key_with_changed_fields_is_conflict(
    scan_client: AsyncClient, scan_auth_headers, scan_image_bytes
) -> None:
    headers = await scan_auth_headers("finalize-key-owner")
    scan = await _analyzed_scan(scan_client, headers, scan_image_bytes())
    request_headers = {**headers, "Idempotency-Key": "finalize-changed"}
    first = await scan_client.post(
        f"/api/v1/scan-sessions/{scan['id']}/finalize",
        json={},
        headers=request_headers,
    )
    changed = await scan_client.post(
        f"/api/v1/scan-sessions/{scan['id']}/finalize",
        json={"brand": "修改后的品牌"},
        headers=request_headers,
    )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_conflict"


@pytest.mark.asyncio
async def test_thumbnail_is_owner_scoped_and_strips_metadata(
    scan_client: AsyncClient, scan_auth_headers, scan_image_bytes
) -> None:
    owner = await scan_auth_headers("thumbnail-owner")
    stranger = await scan_auth_headers("thumbnail-stranger")
    scan = await _analyzed_scan(scan_client, owner, scan_image_bytes())
    finalized = await scan_client.post(
        f"/api/v1/scan-sessions/{scan['id']}/finalize",
        json={},
        headers={**owner, "Idempotency-Key": "thumbnail-finalize"},
    )
    assert finalized.status_code == 201
    food = finalized.json()["food"]

    assert "thumbnail_path" not in food
    assert food["thumbnail_url"] == f"/api/v1/foods/{food['id']}/thumbnail"
    owned = await scan_client.get(food["thumbnail_url"], headers=owner)
    forbidden = await scan_client.get(food["thumbnail_url"], headers=stranger)

    assert owned.status_code == 200
    assert owned.headers["content-type"].startswith("image/jpeg")
    with Image.open(BytesIO(owned.content)) as image:
        assert max(image.size) <= 480
        assert image.getexif() == {}
    assert forbidden.status_code == 404

