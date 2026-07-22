from fastapi.testclient import TestClient

from main import app


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_zalo_webhook_is_guarded_until_contract_is_verified() -> None:
    response = TestClient(app).post("/webhooks/zalo", json={"event": "placeholder"})
    assert response.status_code == 501
    assert response.json()["code"] == "ZALO_CONTRACT_NOT_CONFIGURED"
