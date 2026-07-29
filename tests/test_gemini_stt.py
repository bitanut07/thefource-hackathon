import asyncio
import base64
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from voice.gemini_stt import GeminiSpeechToText, GoogleGenAISTTGateway
from voice.service import Transcript
from voice.stt_errors import STTProviderError, STTUnavailableError


class FakeInteractions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeAsyncClient:
    def __init__(self, interactions: FakeInteractions) -> None:
        self.interactions = interactions


class FakeAioContext:
    def __init__(self, interactions: FakeInteractions) -> None:
        self.async_client = FakeAsyncClient(interactions)

    async def __aenter__(self) -> FakeAsyncClient:
        return self.async_client

    async def __aexit__(self, *args: object) -> None:
        del args


class FakeClient:
    def __init__(self, interactions: FakeInteractions) -> None:
        self.aio = FakeAioContext(interactions)


class FailingSTTGateway(GoogleGenAISTTGateway):
    def __init__(self, error: Exception, *, max_retries: int) -> None:
        super().__init__("test-only", timeout_seconds=1, max_retries=max_retries)
        self.error = error
        self.attempts = 0

    async def _transcribe_once(self, *, model: str, audio: bytes, mime_type: str) -> str:
        del model, audio, mime_type
        self.attempts += 1
        raise self.error


def test_google_stt_gateway_uses_inline_audio_without_provider_storage() -> None:
    interactions = FakeInteractions(SimpleNamespace(output_text="Tìm chỗ khám mắt."))
    gateway = GoogleGenAISTTGateway(
        "test-only",
        timeout_seconds=20,
        max_retries=1,
        client_factory=lambda **_kwargs: FakeClient(interactions),
    )

    text = asyncio.run(
        gateway.transcribe(
            model="gemini-3.6-flash",
            audio=b"audio-bytes",
            mime_type="audio/wav",
        )
    )

    assert text == "Tìm chỗ khám mắt."
    call = interactions.calls[0]
    assert call["model"] == "gemini-3.6-flash"
    assert call["store"] is False
    assert call["response_format"] == {"type": "text"}
    assert call["timeout"] == 20.0
    assert call["input"][0]["type"] == "text"
    assert "chỉ transcript" in call["input"][0]["text"]
    assert call["input"][1] == {
        "type": "audio",
        "data": base64.b64encode(b"audio-bytes").decode("ascii"),
        "mime_type": "audio/wav",
    }


def test_gemini_speech_to_text_returns_unknown_confidence() -> None:
    interactions = FakeInteractions(SimpleNamespace(output_text="  Xin chào.  "))
    gateway = GoogleGenAISTTGateway(
        "test-only",
        timeout_seconds=20,
        max_retries=0,
        client_factory=lambda **_kwargs: FakeClient(interactions),
    )
    provider = GeminiSpeechToText(model="gemini-3.6-flash", gateway=gateway)

    transcript = asyncio.run(provider.transcribe(b"audio", "audio/mpeg"))

    assert transcript == Transcript(text="Xin chào.", confidence=None)


@pytest.mark.parametrize("output_text", [None, "", "   "])
def test_google_stt_gateway_rejects_blank_transcript(output_text: object) -> None:
    interactions = FakeInteractions(SimpleNamespace(output_text=output_text))
    gateway = GoogleGenAISTTGateway(
        "test-only",
        timeout_seconds=20,
        max_retries=0,
        client_factory=lambda **_kwargs: FakeClient(interactions),
    )

    with pytest.raises(STTProviderError, match="transcript hợp lệ"):
        asyncio.run(gateway.transcribe(model="stt-model", audio=b"audio", mime_type="audio/wav"))


def test_google_stt_gateway_bounds_retries_and_maps_failures() -> None:
    transport = FailingSTTGateway(httpx.ConnectError("offline"), max_retries=1)
    with pytest.raises(STTUnavailableError, match="kết nối") as transport_error:
        asyncio.run(transport.transcribe(model="stt-model", audio=b"audio", mime_type="audio/wav"))
    assert transport.attempts == 2
    assert transport_error.value.retry_after_seconds == 1

    quota = FailingSTTGateway(
        errors.ClientError(
            429,
            {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}},
        ),
        max_retries=0,
    )
    with pytest.raises(STTUnavailableError) as quota_error:
        asyncio.run(quota.transcribe(model="stt-model", audio=b"audio", mime_type="audio/wav"))
    assert quota_error.value.retry_after_seconds == 1

    client_error = FailingSTTGateway(
        errors.ClientError(400, {"error": {"message": "bad request"}}),
        max_retries=1,
    )
    with pytest.raises(STTProviderError, match="lỗi 400"):
        asyncio.run(
            client_error.transcribe(model="stt-model", audio=b"audio", mime_type="audio/wav")
        )
    assert client_error.attempts == 1


def test_google_stt_gateway_maps_final_timeout() -> None:
    gateway = FailingSTTGateway(TimeoutError("slow"), max_retries=1)

    with pytest.raises(TimeoutError, match="STT vượt quá thời gian"):
        asyncio.run(gateway.transcribe(model="stt-model", audio=b"audio", mime_type="audio/wav"))

    assert gateway.attempts == 2
