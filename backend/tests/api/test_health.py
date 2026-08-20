def test_live_returns_service_identity(client):
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "xianzhi-api"}


def test_ready_reports_injected_dependencies(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "mysql": "ok", "redis": "ok"}
