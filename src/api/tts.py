from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Request, Response, Security, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.security import require_api_key
from config import Settings
from voice.tts import (
    MAX_CHOICE_NAME_LENGTH,
    MAX_CHOICES,
    MAX_MESSAGE_LENGTH,
    TTSProviderError,
    TTSService,
    TTSUnavailableError,
)

logger = logging.getLogger(__name__)

ChoiceName = Annotated[str, Field(min_length=1, max_length=MAX_CHOICE_NAME_LENGTH)]

router = APIRouter(prefix="/api/v1", tags=["text to speech"])


class TTSRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "message": "Mình tìm thấy ba lựa chọn phù hợp.",
                    "choice_names": ["EVNHCMC", "ZaloPay", "MoMo"],
                }
            ]
        },
    )

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    choice_names: list[ChoiceName] = Field(default_factory=list, max_length=MAX_CHOICES)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message không được chỉ chứa khoảng trắng")
        return normalized

    @field_validator("choice_names")
    @classmethod
    def strip_choice_names(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("choice_names không được chỉ chứa khoảng trắng")
        return normalized


@asynccontextmanager
async def _tts_capacity(request: Request) -> AsyncIterator[None]:
    settings = cast(Settings, request.app.state.settings)
    semaphore = cast(asyncio.Semaphore, request.app.state.tts_semaphore)
    try:
        await asyncio.wait_for(
            semaphore.acquire(),
            timeout=settings.tts_queue_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="TTS đang xử lý tối đa số yêu cầu cho phép.",
            headers={"Retry-After": "1"},
        ) from exc
    try:
        yield
    finally:
        semaphore.release()


@router.post(
    "/tts",
    response_class=Response,
    summary="Chuyển lời đáp FOne thành audio WAV",
    description=(
        "Đọc lời đáp và tối đa năm tên dịch vụ bằng giọng tiếng Việt đã cấu hình. "
        "Endpoint không nhận URL và không lưu text hoặc audio."
    ),
    responses={
        200: {
            "description": "WAV mono 24 kHz, 16-bit.",
            "content": {"audio/wav": {}},
        },
        401: {"description": "X-API-Key thiếu hoặc không hợp lệ."},
        422: {"description": "Nội dung TTS không hợp lệ."},
        429: {"description": "Đã đạt giới hạn request TTS đồng thời."},
        502: {"description": "Gemini trả audio không hợp lệ."},
        503: {"description": "TTS bị tắt hoặc tạm thời chưa sẵn sàng."},
        504: {"description": "TTS vượt quá thời gian xử lý."},
    },
    dependencies=[Security(require_api_key)],
)
async def synthesize_tts(payload: TTSRequest, request: Request) -> Response:
    service = cast(TTSService, request.app.state.tts_service)
    settings = cast(Settings, request.app.state.settings)
    started_at = time.perf_counter()
    try:
        async with _tts_capacity(request):
            async with asyncio.timeout(settings.tts_timeout_seconds):
                audio = await service.synthesize_response(
                    payload.message,
                    payload.choice_names,
                )
    except ValueError as exc:
        logger.info("TTS request rejected; code=invalid_content")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Nội dung TTS không hợp lệ.",
        ) from exc
    except TTSProviderError as exc:
        logger.warning("TTS request failed; code=provider_error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini TTS không trả audio hợp lệ.",
        ) from exc
    except TTSUnavailableError as exc:
        logger.warning("TTS request failed; code=unavailable")
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS chưa được bật hoặc tạm thời chưa sẵn sàng.",
            headers=headers,
        ) from exc
    except TimeoutError as exc:
        logger.warning("TTS request failed; code=timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="TTS vượt quá thời gian xử lý cho phép.",
        ) from exc

    latency_ms = round((time.perf_counter() - started_at) * 1_000)
    logger.info(
        "TTS request completed; latency_ms=%d audio_bytes=%d",
        latency_ms,
        len(audio.content),
    )
    return Response(
        content=audio.content,
        media_type=audio.media_type,
        headers={
            "Content-Disposition": 'inline; filename="fone-response.wav"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
