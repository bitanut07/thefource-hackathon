from __future__ import annotations

import re
import unicodedata
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

MAX_MESSAGE_LENGTH = 1_000
MAX_CHOICE_NAME_LENGTH = 120
MAX_CHOICES = 5
MAX_AUDIO_BYTES = 5 * 1024 * 1024
WAV_SAMPLE_RATE_HZ = 24_000
WAV_CHANNELS = 1
WAV_SAMPLE_WIDTH_BYTES = 2

_URL_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)\S+")


class TTSUnavailableError(RuntimeError):
    """The configured text-to-speech provider cannot currently serve a request."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TTSProviderError(RuntimeError):
    """The provider failed or returned audio that cannot be served safely."""


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    content: bytes
    media_type: str
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int


class TextToSpeech(Protocol):
    async def synthesize(self, text: str) -> SynthesizedAudio:
        """Convert trusted application speech text to bounded audio bytes."""
        ...


class SpeechSynthesisGateway(Protocol):
    async def generate_pcm(self, *, model: str, text: str, voice: str) -> bytes:
        """Generate raw mono 24 kHz, 16-bit PCM for a fixed voice."""
        ...


def _normalize_spoken_value(value: str, *, maximum_length: int) -> str:
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("Nội dung TTS không hợp lệ.")
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > maximum_length or _URL_PATTERN.search(normalized):
        raise ValueError("Nội dung TTS không hợp lệ.")
    return normalized


def _pcm_to_wav(pcm: bytes) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(WAV_CHANNELS)
        wav_file.setsampwidth(WAV_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(WAV_SAMPLE_RATE_HZ)
        wav_file.writeframes(pcm)
    return output.getvalue()


class GeminiTextToSpeech:
    """Generate a single-speaker WAV from Gemini-provided raw PCM."""

    def __init__(self, *, model: str, voice: str, gateway: SpeechSynthesisGateway) -> None:
        self._model = model
        self._voice = voice
        self._gateway = gateway

    async def synthesize(self, text: str) -> SynthesizedAudio:
        pcm = await self._gateway.generate_pcm(
            model=self._model,
            text=text,
            voice=self._voice,
        )
        if not pcm:
            raise TTSProviderError("Gemini không trả audio hợp lệ.")
        wav = _pcm_to_wav(pcm)
        if len(wav) > MAX_AUDIO_BYTES:
            raise TTSProviderError("Audio TTS vượt quá 5 MiB.")
        return SynthesizedAudio(
            content=wav,
            media_type="audio/wav",
            sample_rate_hz=WAV_SAMPLE_RATE_HZ,
            channels=WAV_CHANNELS,
            sample_width_bytes=WAV_SAMPLE_WIDTH_BYTES,
        )


class TTSService:
    """Apply FOne's speech-content policy before calling a provider."""

    def __init__(self, synthesizer: TextToSpeech) -> None:
        self._synthesizer = synthesizer

    async def synthesize_response(
        self,
        message: str,
        choice_names: list[str],
    ) -> SynthesizedAudio:
        normalized_message = _normalize_spoken_value(
            message,
            maximum_length=MAX_MESSAGE_LENGTH,
        )
        if len(choice_names) > MAX_CHOICES:
            raise ValueError("Nội dung TTS không hợp lệ.")

        normalized_choices: list[str] = []
        seen: set[str] = set()
        for choice_name in choice_names:
            normalized = _normalize_spoken_value(
                choice_name,
                maximum_length=MAX_CHOICE_NAME_LENGTH,
            )
            deduplication_key = normalized.casefold()
            if deduplication_key not in seen:
                seen.add(deduplication_key)
                normalized_choices.append(normalized)

        speech_text = normalized_message
        if normalized_choices:
            speech_text += f" Các lựa chọn gồm: {', '.join(normalized_choices)}."
        return await self._synthesizer.synthesize(speech_text)
