import pytest
from httpx import AsyncClient


async def _start(client: AsyncClient, headers: dict[str, str], scenario: str) -> str:
    response = await client.post(
        "/api/v1/scan-sessions",
        json={"mock_scenario": scenario},
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["id"])


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    scan_id: str,
    content: bytes,
    *,
    purpose: str,
    key: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/frames",
        files={"image": (f"{key}.jpg", content, "image/jpeg")},
        data={"purpose": purpose},
        headers={**headers, "Idempotency-Key": key},
    )
    assert response.status_code == 202
    current = await client.get(f"/api/v1/scan-sessions/{scan_id}", headers=headers)
    assert current.status_code == 200
    return dict(current.json())


async def _finalize(
    client: AsyncClient,
    headers: dict[str, str],
    scan_id: str,
    fields: dict[str, object],
    key: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/scan-sessions/{scan_id}/finalize",
        json=fields,
        headers={**headers, "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return dict(response.json()["food"])


@pytest.mark.asyncio
async def test_packaged_food_scans_and_finalizes(
    scan_client: AsyncClient, scan_auth_headers, scan_image_bytes
) -> None:
    headers = await scan_auth_headers("e2e-packaged")
    scan_id = await _start(scan_client, headers, "packaged_success")
    scan = await _upload(
        scan_client,
        headers,
        scan_id,
        scan_image_bytes("vertical"),
        purpose="general",
        key="packaged-frame",
    )

    assert scan["status"] == "ready"
    food = await _finalize(scan_client, headers, scan_id, {}, "packaged-finalize")
    assert food["food_name"] == "伊利鲜牛奶"
    assert food["recommended_consume_by"] == "2026-08-25"


@pytest.mark.asyncio
async def test_identity_failure_requests_and_uses_front_frame(
    scan_client: AsyncClient, scan_auth_headers, scan_image_bytes
) -> None:
    headers = await scan_auth_headers("e2e-identity")
    scan_id = await _start(scan_client, headers, "needs_identity")
    first = await _upload(
        scan_client,
        headers,
        scan_id,
        scan_image_bytes("vertical"),
        purpose="date",
        key="identity-date-frame",
    )
    assert first["status"] == "needs_input"
    assert first["missing_fields"] == ["food_name"]

    second = await _upload(
        scan_client,
        headers,
        scan_id,
        scan_image_bytes("horizontal"),
        purpose="identity",
        key="identity-front-frame",
    )
    assert second["status"] == "ready"
    food = await _finalize(scan_client, headers, scan_id, {}, "identity-finalize")
    assert food["food_name"] == "伊利鲜牛奶"


@pytest.mark.asyncio
async def test_fresh_produce_asks_storage_then_uses_knowledge_rule(
    scan_client: AsyncClient, scan_auth_headers, scan_image_bytes
) -> None:
    headers = await scan_auth_headers("e2e-fresh")
    scan_id = await _start(scan_client, headers, "fresh_produce")
    scan = await _upload(
        scan_client,
        headers,
        scan_id,
        scan_image_bytes("vertical"),
        purpose="general",
        key="fresh-frame",
    )
    assert scan["status"] == "needs_input"
    assert scan["missing_fields"] == ["storage_type"]

    food = await _finalize(
        scan_client,
        headers,
        scan_id,
        {"storage_type": "chilled"},
        "fresh-finalize",
    )
    assert food["food_name"] == "草莓"
    assert food["recommended_consume_by"] == "2026-08-25"
    assert food["date_basis"] == "knowledge_base_estimate"
