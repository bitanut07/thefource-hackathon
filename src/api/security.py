import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, NoReturn, cast

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from config import Settings
from llm.client import LLMProviderError, LLMUnavailableError

MIN_NAVIGATOR_API_KEY_LENGTH = 16

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="NavigatorApiKey",
    description="Nhập NAVIGATOR_API_KEY để gọi API điều hướng và dữ liệu kiểm thử.",
    auto_error=False,
)


def configured_navigator_api_key(settings: Settings) -> str:
    """Return the configured client key only when it meets the safety floor."""

    value = (
        settings.navigator_api_key.get_secret_value().strip()
        if settings.navigator_api_key is not None
        else ""
    )
    return value if len(value) >= MIN_NAVIGATOR_API_KEY_LENGTH else ""


def require_api_key(
    request: Request,
    supplied_key: Annotated[str | None, Security(api_key_header)] = None,
) -> None:
    """Authenticate a caller without ever logging or returning either key."""

    settings = cast(Settings, request.app.state.settings)
    configured_key = configured_navigator_api_key(settings)
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Navigator API chưa được cấu hình khóa truy cập.",
        )
    if supplied_key is None or not secrets.compare_digest(supplied_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Khóa truy cập không hợp lệ.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


@asynccontextmanager
async def navigator_capacity(request: Request) -> AsyncIterator[None]:
    """Apply the process-local Gemini concurrency limit."""

    settings = cast(Settings, request.app.state.settings)
    semaphore = cast(asyncio.Semaphore, request.app.state.navigator_semaphore)
    try:
        await asyncio.wait_for(
            semaphore.acquire(),
            timeout=settings.navigator_queue_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Navigator đang xử lý tối đa số yêu cầu cho phép.",
            headers={"Retry-After": "1"},
        ) from exc

    try:
        yield
    finally:
        semaphore.release()


def raise_llm_http_error(exc: LLMUnavailableError | LLMProviderError) -> NoReturn:
    """Map provider failures to a stable public API contract."""

    if isinstance(exc, LLMUnavailableError):
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini chưa được cấu hình hoặc tạm thời chưa sẵn sàng.",
            headers=headers,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Gemini không trả kết quả có cấu trúc hợp lệ.",
    ) from exc
