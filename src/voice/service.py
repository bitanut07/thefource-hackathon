from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    confidence: float | None


class SpeechToText(Protocol):
    async def transcribe(self, audio_path: Path) -> Transcript:
        # TODO: Chuyển audio tạm thành transcript tiếng Việt.
        raise NotImplementedError("Chưa triển khai contract chuyển giọng nói thành văn bản")


class VoiceService:
    speech_to_text: SpeechToText

    def __init__(self, speech_to_text: SpeechToText) -> None:
        # TODO: Gắn adapter STT và chính sách xử lý audio tạm.
        raise NotImplementedError("Chưa triển khai khởi tạo dịch vụ giọng nói")

    async def transcribe(self, audio_path: Path) -> Transcript:
        # TODO: Chuyển audio thành transcript và áp dụng luồng xác nhận confidence.
        raise NotImplementedError("Chưa triển khai xử lý giọng nói")
