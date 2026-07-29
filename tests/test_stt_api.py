import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from config import Settings
from voice.service import MAX_STT_AUDIO_BYTES, Transcript
from voice.stt_errors import STTProviderError, STTUnavailableError

API_HEADERS = {"X-API-Key": "test-navigator-key", "Content-Type": "audio/wav"}


class StubVoiceService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        self.calls.append((audio, mime_type))
        if self.error is not None:
            raise self.error
        return Transcript(text="Tìm chỗ khám mắt.", confidence=None)


def _create_app(
    monkeypatch: pytest.MonkeyPatch,
    service: StubVoiceService,
    **settings_overrides: Any,
) -> FastAPI:
    monkeypatch.setattr(
        main,
        "build_stt_service",
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


def test_stt_endpoint_transcribes_raw_audio_without_persisting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubVoiceService()
    response = TestClient(_create_app(monkeypatch, service)).post(
        "/api/v1/stt",
        content=b"audio-bytes",
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Tìm chỗ khám mắt.", "confidence": None}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert service.calls == [(b"audio-bytes", "audio/wav")]


def test_stt_endpoint_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    service = StubVoiceService()
    response = TestClient(_create_app(monkeypatch, service)).post(
        "/api/v1/stt",
        content=b"audio",
        headers={"Content-Type": "audio/wav"},
    )

    assert response.status_code == 401
    assert service.calls == []


@pytest.mark.parametrize(
    ("content", "headers", "expected_status"),
    [
        (b"", API_HEADERS, 422),
        (b"audio", {**API_HEADERS, "Content-Type": "application/octet-stream"}, 415),
        (
            b"small",
            {**API_HEADERS, "Content-Length": str(MAX_STT_AUDIO_BYTES + 1)},
            413,
        ),
    ],
)
def test_stt_endpoint_rejects_invalid_audio_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    service = StubVoiceService()
    response = TestClient(_create_app(monkeypatch, service)).post(
        "/api/v1/stt",
        content=content,
        headers=headers,
    )

    assert response.status_code == expected_status
    assert service.calls == []


def test_stt_endpoint_stops_chunked_upload_after_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubVoiceService()

    def oversized_chunks() -> Iterator[bytes]:
        yield b"x" * MAX_STT_AUDIO_BYTES
        yield b"x"

    response = TestClient(_create_app(monkeypatch, service)).post(
        "/api/v1/stt",
        content=oversized_chunks(),
        headers=API_HEADERS,
    )

    assert response.status_code == 413
    assert service.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (STTProviderError("provider details"), 502),
        (STTUnavailableError("unavailable"), 503),
        (TimeoutError("slow"), 504),
    ],
)
def test_stt_endpoint_maps_failures_without_leaking_provider_details(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    response = TestClient(_create_app(monkeypatch, StubVoiceService(error=error))).post(
        "/api/v1/stt",
        content=b"audio",
        headers=API_HEADERS,
    )

    assert response.status_code == expected_status
    assert "provider details" not in response.text


def test_stt_endpoint_returns_retry_after_when_capacity_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _create_app(
        monkeypatch,
        StubVoiceService(),
        stt_queue_timeout_seconds=0.01,
    )
    app.state.stt_semaphore = asyncio.Semaphore(0)

    response = TestClient(app).post(
        "/api/v1/stt",
        content=b"audio",
        headers=API_HEADERS,
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"


def test_openapi_documents_binary_stt_request_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = TestClient(_create_app(monkeypatch, StubVoiceService())).get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/stt"]["post"]
    assert {"NavigatorApiKey": []} in operation["security"]
    request_content = operation["requestBody"]["content"]
    assert request_content["audio/wav"]["schema"] == {"type": "string", "format": "binary"}
    assert operation["responses"]["200"]["content"]["application/json"]
