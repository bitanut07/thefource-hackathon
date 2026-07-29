import asyncio
import wave
from io import BytesIO

import pytest
from pydantic import SecretStr

from config import Settings
from voice.factory import build_tts_service
from voice.tts import (
    MAX_AUDIO_BYTES,
    GeminiTextToSpeech,
    SynthesizedAudio,
    TTSProviderError,
    TTSService,
    TTSUnavailableError,
)


class RecordingSynthesizer:
    def __init__(self, audio: SynthesizedAudio) -> None:
        self.audio = audio
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> SynthesizedAudio:
        self.texts.append(text)
        return self.audio


class RecordingGateway:
    def __init__(self, pcm: bytes) -> None:
        self.pcm = pcm
        self.calls: list[dict[str, str]] = []

    async def generate_pcm(self, *, model: str, text: str, voice: str) -> bytes:
        self.calls.append({"model": model, "text": text, "voice": voice})
        return self.pcm


def _wav_audio() -> SynthesizedAudio:
    return SynthesizedAudio(
        content=b"RIFFtestWAVE",
        media_type="audio/wav",
        sample_rate_hz=24_000,
        channels=1,
        sample_width_bytes=2,
    )


def test_tts_service_builds_compact_speech_and_deduplicates_choices() -> None:
    synthesizer = RecordingSynthesizer(_wav_audio())
    service = TTSService(synthesizer)

    audio = asyncio.run(
        service.synthesize_response(
            "  Mình tìm thấy các dịch vụ phù hợp.  ",
            [" EVNHCMC ", "ZaloPay", "evnhcmc"],
        )
    )

    assert audio == _wav_audio()
    assert synthesizer.texts == [
        "Mình tìm thấy các dịch vụ phù hợp. Các lựa chọn gồm: EVNHCMC, ZaloPay."
    ]


@pytest.mark.parametrize(
    ("message", "choices"),
    [
        ("Xem tại https://example.com", []),
        ("Mình tìm thấy dịch vụ.", ["www.example.com"]),
        ("Nội dung\nkhông hợp lệ", []),
        ("Nội dung hợp lệ", ["Tên\tdịch vụ"]),
    ],
)
def test_tts_service_rejects_urls_and_control_characters(
    message: str,
    choices: list[str],
) -> None:
    service = TTSService(RecordingSynthesizer(_wav_audio()))

    with pytest.raises(ValueError, match="Nội dung TTS không hợp lệ"):
        asyncio.run(service.synthesize_response(message, choices))


def test_gemini_tts_wraps_pcm_in_a_standard_wave_container() -> None:
    gateway = RecordingGateway(b"\x01\x02\x03\x04")
    synthesizer = GeminiTextToSpeech(
        model="gemini-3.1-flash-tts-preview",
        voice="Kore",
        gateway=gateway,
    )

    audio = asyncio.run(synthesizer.synthesize("Xin chào."))

    assert audio.media_type == "audio/wav"
    assert audio.content.startswith(b"RIFF")
    assert audio.content[8:12] == b"WAVE"
    with wave.open(BytesIO(audio.content), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 24_000
        assert wav_file.getsampwidth() == 2
        assert wav_file.readframes(wav_file.getnframes()) == b"\x01\x02\x03\x04"
    assert gateway.calls == [
        {
            "model": "gemini-3.1-flash-tts-preview",
            "text": "Xin chào.",
            "voice": "Kore",
        }
    ]


def test_gemini_tts_rejects_empty_or_oversized_audio() -> None:
    empty = GeminiTextToSpeech(model="tts-model", voice="Kore", gateway=RecordingGateway(b""))
    oversized = GeminiTextToSpeech(
        model="tts-model",
        voice="Kore",
        gateway=RecordingGateway(b"x" * MAX_AUDIO_BYTES),
    )

    with pytest.raises(TTSProviderError, match="audio hợp lệ"):
        asyncio.run(empty.synthesize("Xin chào."))
    with pytest.raises(TTSProviderError, match="vượt quá 5 MiB"):
        asyncio.run(oversized.synthesize("Xin chào."))


def test_tts_factory_is_disabled_by_default_and_requires_gemini_key() -> None:
    disabled = build_tts_service(Settings())
    missing_key = build_tts_service(Settings(tts_provider="gemini", gemini_api_key=SecretStr("")))

    with pytest.raises(TTSUnavailableError, match="chưa được bật"):
        asyncio.run(disabled.synthesize_response("Xin chào.", []))
    with pytest.raises(TTSUnavailableError, match="chưa được cấu hình"):
        asyncio.run(missing_key.synthesize_response("Xin chào.", []))


def test_tts_factory_builds_configured_gemini_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = RecordingGateway(b"\x01\x02")
    monkeypatch.setattr(
        "voice.factory.GoogleGenAISpeechGateway",
        lambda *_args, **_kwargs: gateway,
    )
    service = build_tts_service(
        Settings(
            tts_provider="gemini",
            tts_model="tts-model",
            tts_voice="Kore",
            gemini_api_key=SecretStr("test-only"),
        )
    )

    audio = asyncio.run(service.synthesize_response("Xin chào.", []))

    assert audio.content.startswith(b"RIFF")
    assert gateway.calls == [{"model": "tts-model", "text": "Xin chào.", "voice": "Kore"}]
