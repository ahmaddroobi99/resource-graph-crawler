from fastapi.testclient import TestClient

from service.app import app


client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"]


def test_status_shape():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert "target" in body
    assert "limits" in body


def test_console_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "RESOURCE GRAPH CRAWLER" in response.text
