from pydantic import SecretStr

from config import Settings
from voice.gemini_stt import GeminiSpeechToText, GoogleGenAISTTGateway
from voice.gemini_tts import GoogleGenAISpeechGateway
from voice.service import Transcript, VoiceService
from voice.stt_errors import STTUnavailableError
from voice.tts import (
    GeminiTextToSpeech,
    SynthesizedAudio,
    TTSService,
    TTSUnavailableError,
)


class UnavailableTextToSpeech:
    def __init__(self, message: str) -> None:
        self._message = message

    async def synthesize(self, text: str) -> SynthesizedAudio:
        del text
        raise TTSUnavailableError(self._message)


class UnavailableSpeechToText:
    def __init__(self, message: str) -> None:
        self._message = message

    async def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        del audio, mime_type
        raise STTUnavailableError(self._message)


def _secret_value(value: SecretStr | None) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def build_stt_service(settings: Settings) -> VoiceService:
    """Build the opt-in STT service without uploading or persisting audio."""

    if settings.stt_provider == "disabled":
        return VoiceService(UnavailableSpeechToText("STT chưa được bật."))

    api_key = _secret_value(settings.stt_api_key) or _secret_value(settings.gemini_api_key)
    if not api_key:
        return VoiceService(UnavailableSpeechToText("Gemini STT chưa được cấu hình."))

    model = settings.stt_model.strip()
    if not model:
        raise ValueError("STT_MODEL không được để trống khi bật STT.")
    gateway = GoogleGenAISTTGateway(
        api_key,
        timeout_seconds=settings.stt_timeout_seconds,
        max_retries=settings.stt_max_retries,
    )
    return VoiceService(GeminiSpeechToText(model=model, gateway=gateway))


def build_tts_service(settings: Settings) -> TTSService:
    """Build the opt-in TTS service without making a provider request."""

    if settings.tts_provider == "disabled":
        return TTSService(UnavailableTextToSpeech("TTS chưa được bật."))

    api_key = _secret_value(settings.gemini_api_key)
    if not api_key:
        return TTSService(UnavailableTextToSpeech("Gemini TTS chưa được cấu hình."))

    model = settings.tts_model.strip()
    voice = settings.tts_voice.strip()
    if not model or not voice:
        raise ValueError("TTS_MODEL và TTS_VOICE không được để trống khi bật TTS.")
    gateway = GoogleGenAISpeechGateway(
        api_key,
        timeout_seconds=settings.tts_timeout_seconds,
        max_retries=settings.tts_max_retries,
    )
    return TTSService(GeminiTextToSpeech(model=model, voice=voice, gateway=gateway))
