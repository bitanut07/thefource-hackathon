from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response, Security, status
from pydantic import BaseModel

from api.security import require_api_key
from config import Settings
from voice.service import (
    MAX_STT_AUDIO_BYTES,
    SUPPORTED_STT_MIME_TYPES,
    VoiceService,
)
from voice.stt_errors import STTProviderError, STTUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["speech to text"])

_BINARY_SCHEMA = {"schema": {"type": "string", "format": "binary"}}
_STT_REQUEST_CONTENT = {mime_type: _BINARY_SCHEMA for mime_type in sorted(SUPPORTED_STT_MIME_TYPES)}


class STTResponse(BaseModel):
    text: str
    confidence: float | None = None


@asynccontextmanager
async def _stt_capacity(request: Request) -> AsyncIterator[None]:
    settings = cast(Settings, request.app.state.settings)
    semaphore = cast(asyncio.Semaphore, request.app.state.stt_semaphore)
    try:
        await asyncio.wait_for(
            semaphore.acquire(),
            timeout=settings.stt_queue_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="STT đang xử lý tối đa số yêu cầu cho phép.",
            headers={"Retry-After": "1"},
        ) from exc
    try:
        yield
    finally:
        semaphore.release()


def _request_mime_type(request: Request) -> str:
    return request.headers.get("content-type", "").partition(";")[0].strip().casefold()


def _validate_declared_size(request: Request) -> None:
    raw_content_length = request.headers.get("content-length")
    if raw_content_length is None:
        return
    try:
        content_length = int(raw_content_length)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Length không hợp lệ.",
        ) from exc
    if content_length < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Length không hợp lệ.",
        )
    if content_length > MAX_STT_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio STT vượt quá 10 MiB.",
        )


async def _read_bounded_audio(request: Request) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_STT_AUDIO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Audio STT vượt quá 10 MiB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/stt",
    response_model=STTResponse,
    summary="Chuyển audio thành transcript tiếng Việt",
    description=(
        "Nhận trực tiếp audio nhị phân tối đa 10 MiB, xử lý trong bộ nhớ và không "
        "lưu file hoặc transcript."
    ),
    responses={
        401: {"description": "X-API-Key thiếu hoặc không hợp lệ."},
        413: {"description": "Audio vượt quá 10 MiB."},
        415: {"description": "MIME type audio không được hỗ trợ."},
        422: {"description": "Audio rỗng hoặc không hợp lệ."},
        429: {"description": "Đã đạt giới hạn request STT đồng thời."},
        502: {"description": "Gemini không trả transcript hợp lệ."},
        503: {"description": "STT bị tắt hoặc tạm thời chưa sẵn sàng."},
        504: {"description": "STT vượt quá thời gian xử lý."},
    },
    dependencies=[Security(require_api_key)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": _STT_REQUEST_CONTENT,
        }
    },
)
async def transcribe_stt(request: Request, response: Response) -> STTResponse:
    mime_type = _request_mime_type(request)
    if mime_type not in SUPPORTED_STT_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Định dạng audio STT không được hỗ trợ.",
        )
    _validate_declared_size(request)
    audio = await _read_bounded_audio(request)
    if not audio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Audio STT không được rỗng.",
        )
    if len(audio) > MAX_STT_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio STT vượt quá 10 MiB.",
        )

    service = cast(VoiceService, request.app.state.stt_service)
    settings = cast(Settings, request.app.state.settings)
    started_at = time.perf_counter()
    try:
        async with _stt_capacity(request):
            async with asyncio.timeout(settings.stt_timeout_seconds):
                transcript = await service.transcribe(audio, mime_type)
    except ValueError as exc:
        logger.info("STT request rejected; code=invalid_audio")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Audio STT không hợp lệ.",
        ) from exc
    except STTProviderError as exc:
        logger.warning("STT request failed; code=provider_error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini STT không trả transcript hợp lệ.",
        ) from exc
    except STTUnavailableError as exc:
        logger.warning("STT request failed; code=unavailable")
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STT chưa được bật hoặc tạm thời chưa sẵn sàng.",
            headers=headers,
        ) from exc
    except TimeoutError as exc:
        logger.warning("STT request failed; code=timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="STT vượt quá thời gian xử lý cho phép.",
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    latency_ms = round((time.perf_counter() - started_at) * 1_000)
    logger.info(
        "STT request completed; latency_ms=%d audio_bytes=%d",
        latency_ms,
        len(audio),
    )
    return STTResponse(text=transcript.text, confidence=transcript.confidence)
