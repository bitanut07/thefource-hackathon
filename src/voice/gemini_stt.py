from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from google import genai
from google.genai import errors

from voice.service import Transcript
from voice.stt_errors import STTProviderError, STTUnavailableError

_TRANSCRIPTION_PROMPT = (
    "Chuyển lời nói trong audio thành văn bản tiếng Việt. "
    "Trả về chỉ transcript nguyên văn, không Markdown, timestamp, giải thích hoặc bản dịch."
)


class AudioTranscriptionGateway(Protocol):
    async def transcribe(self, *, model: str, audio: bytes, mime_type: str) -> str:
        """Return plain transcript text for bounded inline audio."""
        ...


class GoogleGenAISTTGateway:
    """Gemini Interactions adapter for bounded inline audio transcription."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: int,
        max_retries: int,
        client_factory: Callable[..., Any] = genai.Client,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client_factory = client_factory

    async def transcribe(self, *, model: str, audio: bytes, mime_type: str) -> str:
        for attempt in range(self._max_retries + 1):
            try:
                return await self._transcribe_once(
                    model=model,
                    audio=audio,
                    mime_type=mime_type,
                )
            except errors.APIError as exc:
                is_retriable = exc.code == 429 or exc.code >= 500
                if is_retriable and attempt >= self._max_retries:
                    raise STTUnavailableError(
                        "Gemini STT tạm thời không sẵn sàng.",
                        retry_after_seconds=1,
                    ) from exc
                if not is_retriable:
                    raise STTProviderError(
                        f"Gemini STT trả lỗi {exc.code}; response provider không được ghi log."
                    ) from exc
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise STTUnavailableError(
                        "Không thể kết nối ổn định tới Gemini STT.",
                        retry_after_seconds=1,
                    ) from exc
            except TimeoutError as exc:
                if attempt >= self._max_retries:
                    raise TimeoutError("STT vượt quá thời gian xử lý cho phép.") from exc
            except errors.UnknownApiResponseError as exc:
                raise STTProviderError("Gemini STT trả response không thể đọc an toàn.") from exc

            await asyncio.sleep(min(0.25 * (2**attempt), 2.0))

        raise AssertionError("unreachable retry state")

    async def _transcribe_once(self, *, model: str, audio: bytes, mime_type: str) -> str:
        client = self._client_factory(
            api_key=self._api_key,
            http_options={"api_version": "v1beta"},
        )
        # Source: https://ai.google.dev/gemini-api/docs/audio#pass-audio-data-inline
        async with client.aio as async_client:
            interaction = await async_client.interactions.create(
                model=model,
                input=[
                    {"type": "text", "text": _TRANSCRIPTION_PROMPT},
                    {
                        "type": "audio",
                        "data": base64.b64encode(audio).decode("ascii"),
                        "mime_type": mime_type,
                    },
                ],
                store=False,
                response_format={"type": "text"},
                timeout=float(self._timeout_seconds),
            )

        output_text = getattr(interaction, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise STTProviderError("Gemini STT không trả transcript hợp lệ.")
        return output_text.strip()


class GeminiSpeechToText:
    def __init__(self, *, model: str, gateway: AudioTranscriptionGateway) -> None:
        self._model = model
        self._gateway = gateway

    async def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        text = await self._gateway.transcribe(
            model=self._model,
            audio=audio,
            mime_type=mime_type,
        )
        return Transcript(text=text.strip(), confidence=None)
