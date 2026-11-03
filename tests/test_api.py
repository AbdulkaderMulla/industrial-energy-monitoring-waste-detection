from fastapi.testclient import TestClient
from app.main import app

def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_production_endpoint_shape():
    response = TestClient(app).get("/analytics/production")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        payload = response.json()
        assert "batch_detail" in payload
        assert "machine_summary" in payload
