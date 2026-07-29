import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from config import Settings
from voice.tts import (
    SynthesizedAudio,
    TTSProviderError,
    TTSUnavailableError,
)

API_HEADERS = {"X-API-Key": "test-navigator-key"}


class StubTTSService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.calls: list[tuple[str, list[str]]] = []

    async def synthesize_response(
        self,
        message: str,
        choice_names: list[str],
    ) -> SynthesizedAudio:
        self.calls.append((message, choice_names))
        if self.error is not None:
            raise self.error
        return SynthesizedAudio(
            content=b"RIFFtestWAVE",
            media_type="audio/wav",
            sample_rate_hz=24_000,
            channels=1,
            sample_width_bytes=2,
        )


def _create_app(
    monkeypatch: pytest.MonkeyPatch,
    service: StubTTSService,
    **settings_overrides: Any,
) -> FastAPI:
    monkeypatch.setattr(
        main,
        "build_tts_service",
        lambda _settings: service,
        raising=False,
    )
    return main.create_app(
        Settings(
            search_backend="json",
            allowed_launch_hosts="zalo.me",
            navigator_api_key=SecretStr("test-navigator-key"),
            **settings_overrides,
        )
    )


def test_tts_endpoint_returns_uncached_inline_wave_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubTTSService()
    client = TestClient(_create_app(monkeypatch, service))

    response = client.post(
        "/api/v1/tts",
        json={
            "message": "  Mình tìm thấy các dịch vụ phù hợp.  ",
            "choice_names": [" EVNHCMC ", "ZaloPay"],
        },
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    assert response.content == b"RIFFtestWAVE"
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["content-disposition"] == 'inline; filename="fone-response.wav"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert service.calls == [("Mình tìm thấy các dịch vụ phù hợp.", ["EVNHCMC", "ZaloPay"])]


def test_tts_endpoint_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    service = StubTTSService()
    client = TestClient(_create_app(monkeypatch, service))

    response = client.post("/api/v1/tts", json={"message": "Xin chào."})

    assert response.status_code == 401
    assert service.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "   "},
        {"message": "Xin chào.", "choice_names": ["a"] * 6},
        {"message": "Xin chào.", "choice_names": ["   "]},
        {"message": "Xin chào.", "unexpected": True},
    ],
)
def test_tts_endpoint_rejects_invalid_request_schema(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    service = StubTTSService()
    client = TestClient(_create_app(monkeypatch, service))

    response = client.post("/api/v1/tts", json=payload, headers=API_HEADERS)

    assert response.status_code == 422
    assert service.calls == []


def test_tts_endpoint_maps_content_policy_failure_to_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubTTSService(error=ValueError("Nội dung TTS không hợp lệ."))
    client = TestClient(_create_app(monkeypatch, service))

    response = client.post(
        "/api/v1/tts",
        json={"message": "Xem tại https://example.com"},
        headers=API_HEADERS,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Nội dung TTS không hợp lệ."}


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (TTSProviderError("provider details"), 502),
        (TTSUnavailableError("unavailable"), 503),
        (TimeoutError("slow"), 504),
    ],
)
def test_tts_endpoint_maps_failures_without_leaking_provider_details(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    client = TestClient(_create_app(monkeypatch, StubTTSService(error=error)))

    response = client.post(
        "/api/v1/tts",
        json={"message": "Xin chào."},
        headers=API_HEADERS,
    )

    assert response.status_code == expected_status
    assert "provider details" not in response.text


def test_tts_endpoint_returns_retry_after_when_capacity_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _create_app(
        monkeypatch,
        StubTTSService(),
        tts_queue_timeout_seconds=0.01,
    )
    app.state.tts_semaphore = asyncio.Semaphore(0)

    response = TestClient(app).post(
        "/api/v1/tts",
        json={"message": "Xin chào."},
        headers=API_HEADERS,
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"


def test_openapi_documents_tts_api_key_and_wave_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = TestClient(_create_app(monkeypatch, StubTTSService())).get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/tts"]["post"]
    request_schema = schema["components"]["schemas"]["TTSRequest"]
    assert {"NavigatorApiKey": []} in operation["security"]
    assert "audio/wav" in operation["responses"]["200"]["content"]
    assert request_schema["additionalProperties"] is False
    assert request_schema["properties"]["message"]["maxLength"] == 1_000
    assert request_schema["properties"]["choice_names"]["maxItems"] == 5


def test_disabled_tts_does_not_affect_liveness(monkeypatch: pytest.MonkeyPatch) -> None:
    service = StubTTSService(error=TTSUnavailableError("disabled"))
    client = TestClient(_create_app(monkeypatch, service, tts_provider="disabled"))

    assert client.get("/health/live").status_code == 200
    response = client.post(
        "/api/v1/tts",
        json={"message": "Xin chào."},
        headers=API_HEADERS,
    )
    assert response.status_code == 503
