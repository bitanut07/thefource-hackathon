import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from voice.gemini_tts import GoogleGenAISpeechGateway
from voice.tts import TTSProviderError, TTSUnavailableError


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
    def __init__(self, async_client: FakeAsyncClient) -> None:
        self.async_client = async_client

    async def __aenter__(self) -> FakeAsyncClient:
        return self.async_client

    async def __aexit__(self, *args: object) -> None:
        del args


class FakeClient:
    def __init__(self, interactions: FakeInteractions) -> None:
        self.aio = FakeAioContext(FakeAsyncClient(interactions))


class FailingSpeechGateway(GoogleGenAISpeechGateway):
    def __init__(self, error: Exception, *, max_retries: int) -> None:
        super().__init__(
            "test-only",
            timeout_seconds=1,
            max_retries=max_retries,
        )
        self.error = error
        self.attempts = 0

    async def _generate_once(self, *, model: str, text: str, voice: str) -> bytes:
        del model, text, voice
        self.attempts += 1
        raise self.error


def test_google_gateway_uses_current_interactions_audio_contract() -> None:
    interactions = FakeInteractions(SimpleNamespace(output_audio=SimpleNamespace(data="AQIDBA==")))
    client = FakeClient(interactions)
    gateway = GoogleGenAISpeechGateway(
        "test-only",
        timeout_seconds=15,
        max_retries=1,
        client_factory=lambda **_kwargs: client,
    )

    pcm = asyncio.run(
        gateway.generate_pcm(
            model="gemini-3.1-flash-tts-preview",
            text="Xin chào.",
            voice="Kore",
        )
    )

    assert pcm == b"\x01\x02\x03\x04"
    assert len(interactions.calls) == 1
    call = interactions.calls[0]
    assert call["model"] == "gemini-3.1-flash-tts-preview"
    assert call["store"] is False
    assert call["response_format"] == {"type": "audio"}
    assert call["generation_config"] == {"speech_config": [{"voice": "Kore"}]}
    assert call["timeout"] == 15.0
    assert "tiếng Việt" in call["input"]
    assert "NỘI DUNG CẦN ĐỌC NGUYÊN VĂN" in call["input"]
    assert call["input"].endswith("Xin chào.")


@pytest.mark.parametrize("data", ["not-base64!", "", None])
def test_google_gateway_rejects_invalid_audio_payload(data: object) -> None:
    interactions = FakeInteractions(SimpleNamespace(output_audio=SimpleNamespace(data=data)))
    gateway = GoogleGenAISpeechGateway(
        "test-only",
        timeout_seconds=15,
        max_retries=0,
        client_factory=lambda **_kwargs: FakeClient(interactions),
    )

    with pytest.raises(TTSProviderError, match="audio không thể đọc"):
        asyncio.run(gateway.generate_pcm(model="tts-model", text="Xin chào.", voice="Kore"))


def test_google_gateway_bounds_retries_and_maps_provider_failures() -> None:
    transport = FailingSpeechGateway(httpx.ConnectError("offline"), max_retries=1)
    with pytest.raises(TTSUnavailableError, match="kết nối") as transport_error:
        asyncio.run(transport.generate_pcm(model="tts-model", text="Xin chào.", voice="Kore"))
    assert transport.attempts == 2
    assert transport_error.value.retry_after_seconds == 1

    quota = FailingSpeechGateway(
        errors.ClientError(
            429,
            {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}},
        ),
        max_retries=0,
    )
    with pytest.raises(TTSUnavailableError) as quota_error:
        asyncio.run(quota.generate_pcm(model="tts-model", text="Xin chào.", voice="Kore"))
    assert quota.attempts == 1
    assert quota_error.value.retry_after_seconds == 1

    client_error = FailingSpeechGateway(
        errors.ClientError(400, {"error": {"message": "bad request"}}),
        max_retries=1,
    )
    with pytest.raises(TTSProviderError, match="lỗi 400"):
        asyncio.run(client_error.generate_pcm(model="tts-model", text="Xin chào.", voice="Kore"))
    assert client_error.attempts == 1


def test_google_gateway_maps_final_timeout_to_a_distinct_error() -> None:
    gateway = FailingSpeechGateway(TimeoutError("slow"), max_retries=1)

    with pytest.raises(TimeoutError, match="TTS vượt quá thời gian"):
        asyncio.run(gateway.generate_pcm(model="tts-model", text="Xin chào.", voice="Kore"))

    assert gateway.attempts == 2
