from fastapi.testclient import TestClient

from main import app


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_zalo_webhook_acknowledges_registration_without_processing_event() -> None:
    response = TestClient(app).post("/webhooks/zalo", json={"event": "placeholder"})
    assert response.status_code == 200
    assert response.json()["code"] == "ZALO_EVENT_IGNORED"


def test_zalo_webhook_acknowledges_unsigned_console_fixture_without_queuing() -> None:
    response = TestClient(app).post(
        "/webhooks/zalo",
        json={
            "event_name": "user_send_text",
            "sender": {"id": "test-user"},
            "message": {"msg_id": "This is message id", "text": "This is testing message"},
        },
    )
    assert response.status_code == 200
    assert response.json()["code"] == "ZALO_CONSOLE_TEST_ACKNOWLEDGED"
