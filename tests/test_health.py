from fastapi.testclient import TestClient

from main import app


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_zalo_webhook_acknowledges_registration_without_processing_event() -> None:
    response = TestClient(app).post("/webhooks/zalo", json={"event": "placeholder"})
    assert response.status_code == 200
    assert response.json()["code"] == "ZALO_WEBHOOK_ACKNOWLEDGED"
