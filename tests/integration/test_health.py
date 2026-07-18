from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok_with_service_statuses_and_metadata() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["services"] == {"postgres": "ok", "mongo": "ok"}
    assert body["metadata"]["environment"] == "local"

    timestamp = body["metadata"]["timestamp"]
    assert timestamp.endswith("Z")
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
