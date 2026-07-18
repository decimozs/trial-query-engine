from fastapi.testclient import TestClient

from app.main import app


def test_root_serves_frontend_index() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "Trial Query Engine" in response.text
    assert "fetch(\"/auth/login\"" in response.text
    assert "fetch(\"/query\"" in response.text


def test_static_index_served() -> None:
    with TestClient(app) as client:
        response = client.get("/static/index.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Retrieved Sources" in response.text
