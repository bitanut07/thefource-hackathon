import asyncio

import pytest
from pydantic import SecretStr

from config import Settings
from voice.factory import build_stt_service
from voice.service import MAX_STT_AUDIO_BYTES, Transcript, VoiceService
from voice.stt_errors import STTUnavailableError


class RecordingSpeechToText:
    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        self.calls.append((audio, mime_type))
        return self.transcript


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str]] = []

    async def transcribe(self, *, model: str, audio: bytes, mime_type: str) -> str:
        self.calls.append((model, audio, mime_type))
        return "Xin chào."


def test_voice_service_transcribes_supported_audio_without_persisting_it() -> None:
    provider = RecordingSpeechToText(Transcript(text="Tìm chỗ khám mắt.", confidence=None))
    service = VoiceService(provider)

    transcript = asyncio.run(service.transcribe(b"audio-bytes", "audio/wav"))

    assert transcript == Transcript(text="Tìm chỗ khám mắt.", confidence=None)
    assert provider.calls == [(b"audio-bytes", "audio/wav")]


@pytest.mark.parametrize(
    "mime_type",
    ["audio/wav", "audio/mpeg", "audio/mp3", "audio/aiff", "audio/aac", "audio/ogg", "audio/flac"],
)
def test_voice_service_accepts_documented_gemini_audio_types(mime_type: str) -> None:
    provider = RecordingSpeechToText(Transcript(text="Xin chào.", confidence=None))
    service = VoiceService(provider)

    asyncio.run(service.transcribe(b"audio", mime_type))

    assert provider.calls == [(b"audio", mime_type)]


@pytest.mark.parametrize(
    ("audio", "mime_type", "message"),
    [
        (b"", "audio/wav", "không được rỗng"),
        (b"audio", "application/octet-stream", "không được hỗ trợ"),
        (b"x" * (MAX_STT_AUDIO_BYTES + 1), "audio/wav", "vượt quá 10 MiB"),
    ],
)
def test_voice_service_rejects_invalid_audio(
    audio: bytes,
    mime_type: str,
    message: str,
) -> None:
    service = VoiceService(
        RecordingSpeechToText(Transcript(text="Không được gọi.", confidence=None))
    )

    with pytest.raises(ValueError, match=message):
        asyncio.run(service.transcribe(audio, mime_type))


def test_voice_service_rejects_blank_provider_transcript() -> None:
    service = VoiceService(RecordingSpeechToText(Transcript(text="   ", confidence=None)))

    with pytest.raises(ValueError, match="transcript rỗng"):
        asyncio.run(service.transcribe(b"audio", "audio/wav"))


def test_stt_factory_is_disabled_by_default_and_requires_a_key() -> None:
    disabled = build_stt_service(Settings())
    missing_key = build_stt_service(
        Settings(
            stt_provider="gemini",
            stt_api_key=SecretStr(""),
            gemini_api_key=SecretStr(""),
        )
    )

    with pytest.raises(STTUnavailableError, match="chưa được bật"):
        asyncio.run(disabled.transcribe(b"audio", "audio/wav"))
    with pytest.raises(STTUnavailableError, match="chưa được cấu hình"):
        asyncio.run(missing_key.transcribe(b"audio", "audio/wav"))


def test_stt_factory_builds_configured_gemini_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RecordingGateway()
    monkeypatch.setattr(
        "voice.factory.GoogleGenAISTTGateway",
        lambda *_args, **_kwargs: gateway,
    )
    service = build_stt_service(
        Settings(
            stt_provider="gemini",
            stt_model="stt-model",
            stt_api_key=SecretStr("dedicated-test-key"),
            gemini_api_key=SecretStr("fallback-test-key"),
        )
    )

    transcript = asyncio.run(service.transcribe(b"audio", "audio/wav"))

    assert transcript == Transcript(text="Xin chào.", confidence=None)
    assert gateway.calls == [("stt-model", b"audio", "audio/wav")]
