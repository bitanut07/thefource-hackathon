from typing import cast

from fastapi import APIRouter, Request, Security
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.security import (
    navigator_capacity,
    raise_llm_http_error,
    require_api_key,
)
from llm.client import LLMProviderError, LLMUnavailableError
from llm.schemas import AgentResponse
from skills.navigator import NavigatorSkill

router = APIRouter(prefix="/api/v1", tags=["service navigation"])


class NavigateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"text": "Tôi muốn đóng tiền điện ở TP.HCM."},
                {"text": "Tìm chỗ khám mắt cho mẹ ở TP.HCM."},
                {"text": "Là nhân viên VNG, tôi cần mua đồ ăn."},
            ]
        },
    )

    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text không được chỉ chứa khoảng trắng")
        return stripped


def _navigator(request: Request) -> NavigatorSkill:
    return cast(NavigatorSkill, request.app.state.navigator)


@router.post(
    "/navigate",
    response_model=AgentResponse,
    summary="Tìm dịch vụ bằng câu hỏi tự nhiên",
    description=(
        "Gemini trích xuất nhu cầu có cấu trúc; backend chỉ trả tối đa ba "
        "dịch vụ và URL đã được Registry/allowlist cho phép."
    ),
    responses={
        401: {"description": "X-API-Key thiếu hoặc không hợp lệ."},
        429: {"description": "Đã đạt giới hạn request Gemini đồng thời."},
        502: {"description": "Gemini trả kết quả không hợp lệ."},
        503: {"description": "Gemini hoặc cấu hình runtime chưa sẵn sàng."},
    },
    dependencies=[Security(require_api_key)],
)
async def navigate(
    payload: NavigateRequest,
    request: Request,
) -> AgentResponse:
    """Find controlled service candidates for a natural-language text request."""
    try:
        async with navigator_capacity(request):
            return await _navigator(request).process_text(payload.text)
    except (LLMUnavailableError, LLMProviderError) as exc:
        raise_llm_http_error(exc)
