from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import Callable
from typing import Any

import httpx
from google import genai
from google.genai import errors

from voice.tts import TTSProviderError, TTSUnavailableError

_PROMPT_TEMPLATE = """
Tổng hợp giọng nói tiếng Việt với giọng nữ ấm, rõ ràng, thân thiện và tốc độ vừa.
Chỉ đọc nguyên văn phần nội dung sau nhãn; không đọc các chỉ dẫn khác.

NỘI DUNG CẦN ĐỌC NGUYÊN VĂN:
{text}
""".strip()


class GoogleGenAISpeechGateway:
    """Gemini Interactions API adapter with bounded retry and no response storage."""

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

    async def generate_pcm(self, *, model: str, text: str, voice: str) -> bytes:
        for attempt in range(self._max_retries + 1):
            try:
                return await self._generate_once(model=model, text=text, voice=voice)
            except errors.APIError as exc:
                is_retriable = exc.code == 429 or exc.code >= 500
                if is_retriable and attempt >= self._max_retries:
                    raise TTSUnavailableError(
                        "Gemini TTS tạm thời không sẵn sàng.",
                        retry_after_seconds=1,
                    ) from exc
                if not is_retriable:
                    raise TTSProviderError(
                        f"Gemini TTS trả lỗi {exc.code}; response provider không được ghi log."
                    ) from exc
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise TTSUnavailableError(
                        "Không thể kết nối ổn định tới Gemini TTS.",
                        retry_after_seconds=1,
                    ) from exc
            except TimeoutError as exc:
                if attempt >= self._max_retries:
                    raise TimeoutError("TTS vượt quá thời gian xử lý cho phép.") from exc
            except errors.UnknownApiResponseError as exc:
                raise TTSProviderError("Gemini TTS trả response không thể đọc an toàn.") from exc

            await asyncio.sleep(min(0.25 * (2**attempt), 2.0))

        raise AssertionError("unreachable retry state")

    async def _generate_once(self, *, model: str, text: str, voice: str) -> bytes:
        client = self._client_factory(
            api_key=self._api_key,
            http_options={"api_version": "v1beta"},
        )
        # Source: https://ai.google.dev/gemini-api/docs/speech-generation#single-speaker-tts
        async with client.aio as async_client:
            interaction = await async_client.interactions.create(
                model=model,
                input=_PROMPT_TEMPLATE.format(text=text),
                store=False,
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": voice}]},
                timeout=float(self._timeout_seconds),
            )

        output_audio = getattr(interaction, "output_audio", None)
        encoded_audio = getattr(output_audio, "data", None)
        if not isinstance(encoded_audio, str) or not encoded_audio:
            raise TTSProviderError("Gemini TTS trả audio không thể đọc an toàn.")
        try:
            pcm = base64.b64decode(encoded_audio, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TTSProviderError("Gemini TTS trả audio không thể đọc an toàn.") from exc
        if not pcm:
            raise TTSProviderError("Gemini TTS trả audio không thể đọc an toàn.")
        return pcm
