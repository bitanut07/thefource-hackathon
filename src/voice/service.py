from dataclasses import dataclass
from typing import Protocol

MAX_STT_AUDIO_BYTES = 10 * 1024 * 1024
SUPPORTED_STT_MIME_TYPES = frozenset(
    {
        "audio/wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/aiff",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
    }
)


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    confidence: float | None


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        """Transcribe bounded in-memory audio without persisting it."""
        ...


class VoiceService:
    speech_to_text: SpeechToText

    def __init__(self, speech_to_text: SpeechToText) -> None:
        self.speech_to_text = speech_to_text

    async def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        normalized_mime_type = mime_type.strip().casefold()
        if not audio:
            raise ValueError("Audio STT không được rỗng.")
        if len(audio) > MAX_STT_AUDIO_BYTES:
            raise ValueError("Audio STT vượt quá 10 MiB.")
        if normalized_mime_type not in SUPPORTED_STT_MIME_TYPES:
            raise ValueError("Định dạng audio STT không được hỗ trợ.")

        transcript = await self.speech_to_text.transcribe(audio, normalized_mime_type)
        normalized_text = transcript.text.strip()
        if not normalized_text:
            raise ValueError("Provider trả transcript rỗng.")
        return Transcript(text=normalized_text, confidence=transcript.confidence)
