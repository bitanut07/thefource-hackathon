from typing import cast

from fastapi import APIRouter, Request, Security

from api.navigation import NavigateRequest
from api.security import (
    navigator_capacity,
    raise_llm_http_error,
    require_api_key,
)
from llm.client import LLMProviderError, LLMUnavailableError
from llm.schemas import StructuredQuery
from skills.navigator import NavigatorSkill

router = APIRouter(
    prefix="/api/v1/intents",
    tags=["AI inspection"],
    dependencies=[Security(require_api_key)],
)


@router.post(
    "/extract",
    response_model=StructuredQuery,
    summary="Kiểm tra JSON intent do Gemini trích xuất",
    description=(
        "Chỉ trả structured query đã qua Pydantic validation. Endpoint không "
        "tìm dịch vụ và không cho Gemini tạo service ID hoặc URL."
    ),
    responses={
        401: {"description": "X-API-Key thiếu hoặc không hợp lệ."},
        429: {"description": "Đã đạt giới hạn request Gemini đồng thời."},
        502: {"description": "Gemini trả JSON không hợp lệ."},
        503: {"description": "Gemini hoặc cấu hình runtime chưa sẵn sàng."},
    },
)
async def extract_intent(payload: NavigateRequest, request: Request) -> StructuredQuery:
    navigator = cast(NavigatorSkill, request.app.state.navigator)
    try:
        async with navigator_capacity(request):
            return await navigator.intent_extractor.extract_structured_query(payload.text)
    except (LLMUnavailableError, LLMProviderError) as exc:
        raise_llm_http_error(exc)
