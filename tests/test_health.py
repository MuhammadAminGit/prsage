from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root_returns_app_info():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "prsage"
    assert "version" in body
    assert "model" in body
