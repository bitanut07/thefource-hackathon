"""Fast, authenticated endpoint used by Zalo Chatbot Dynamic API."""

import asyncio
import secrets
import unicodedata
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import FileResponse, JSONResponse

from config import Settings
from domain.postgres_registry import CatalogUnavailableError
from domain.registry import ServiceRegistryRepository
from domain.search import SearchService
from llm.schemas import AgentResponse, ServiceCategoryValue, StructuredQuery
from skills.navigator import TemplateResponseComposer
from zalo.chatbot import render_dynamic_response

router = APIRouter(prefix="/integrations/zalo/chatbot", tags=["Zalo Chatbot"])
_MAX_QUERY_LENGTH = 500
_GENERIC_IMAGE_PATH = Path(__file__).with_name("assets") / "chatbot-service-directory.png"
_CATEGORY_KEYWORDS: dict[ServiceCategoryValue, tuple[str, ...]] = {
    "food": ("an uong", "do an", "nha hang", "fast food", "cafe", "ca phe"),
    "education": ("giao duc", "hoc", "hoc tap", "tieng anh", "toan"),
    "shopping": ("mua sam", "sieu thi", "cua hang", "shopping"),
    "finance": ("tai chinh", "ngan hang", "bao hiem", "finance"),
    "utilities": ("dien", "nuoc", "hoa don", "vien thong", "tien ich"),
    "health": ("y te", "suc khoe", "benh vien", "nha thuoc", "kham benh"),
    "government": ("chinh phu", "hanh chinh", "dich vu cong"),
}
_GENERIC_QUERY_TOKENS = frozenset(
    {
        "can",
        "cho",
        "dich",
        "day",
        "gan",
        "giup",
        "minh",
        "mot",
        "muon",
        "nao",
        "o",
        "toi",
        "tim",
        "vu",
    }
)
_FALLBACK = (
    "Mình đang chưa thể tìm dịch vụ ngay lúc này. Bạn thử lại sau ít phút nhé."
)


def _query_from_request(
    q: str | None,
    text: str | None,
    query: str | None,
    message: str | None,
    input_value: str | None,
) -> str | None:
    """Accept documented flow mapping plus aliases convenient for testing.

    The Dynamic API UI controls the inbound variable name.  ``q`` is the
    production convention; aliases avoid silently failing while configuring it.
    """

    for value in (q, text, query, message, input_value):
        normalized = value.strip() if isinstance(value, str) else ""
        if normalized:
            return normalized if len(normalized) <= _MAX_QUERY_LENGTH else None
    return None


def _fallback_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=render_dynamic_response(AgentResponse(message=_FALLBACK)),
        headers={"Cache-Control": "no-store"},
    )


def _generic_image_urls(settings: Settings, response: AgentResponse) -> dict[str, str]:
    """Use a system-owned thumbnail until a service has an approved asset."""

    base_url = settings.public_base_url.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return {}
    image_url = (
        f"{base_url}/integrations/zalo/chatbot/assets/"
        "service-directory.png"
    )
    return {
        str(choice.service_id): image_url
        for choice in response.choices
        if choice.image_url is None
    }


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in without_marks
        ).split()
    )


def _category_for_text(text: str) -> ServiceCategoryValue | None:
    normalized = _normalize_text(text)
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return None


def _structured_query(text: str) -> StructuredQuery:
    category = _category_for_text(text)
    if category is None:
        return StructuredQuery(intent="find_service", service=text)

    residual_tokens = set(_normalize_text(text).split()) - _GENERIC_QUERY_TOKENS
    for keyword in _CATEGORY_KEYWORDS[category]:
        residual_tokens.difference_update(keyword.split())
    has_specific_service = any(len(token) >= 3 for token in residual_tokens)
    return StructuredQuery(
        intent=f"find_{category}_service",
        service=text if has_specific_service else None,
        category=category,
    )


async def _search_response(request: Request, text: str) -> AgentResponse:
    # Do not call the normal NavigatorSkill here: it can make LLM calls whose
    # latency/retries exceed Zalo Chatbot's two-second Dynamic API deadline.
    query = _structured_query(text)
    search = SearchService(
        cast(ServiceRegistryRepository, request.app.state.registry),
        request.app.state.launch_url_policy,
    )
    candidates = await search.search(query, limit=5)
    return await TemplateResponseComposer().compose(query, candidates, text=text)


@router.get("/assets/service-directory.png", include_in_schema=False)
async def service_directory_thumbnail() -> FileResponse:
    """Serve the neutral, system-owned fallback thumbnail over HTTPS."""

    return FileResponse(
        _GENERIC_IMAGE_PATH,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/dynamic")
async def dynamic_reply(
    request: Request,
    q: str | None = None,
    text: str | None = None,
    query: str | None = None,
    message: str | None = None,
    input: str | None = None,  # noqa: A002 - query parameter required by external callers
    x_chatbot_token: str | None = Header(default=None),
) -> JSONResponse:
    """Return a Zalo Chatbot Format payload in a bounded amount of time."""

    settings = cast(Settings, request.app.state.settings)
    configured_token = (
        settings.zalo_chatbot_token.get_secret_value()
        if settings.zalo_chatbot_token is not None
        else ""
    )
    if not configured_token:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"code": "CHATBOT_DISABLED"},
        )
    if x_chatbot_token is None or not secrets.compare_digest(x_chatbot_token, configured_token):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "UNAUTHORIZED"},
        )

    user_text = _query_from_request(q, text, query, message, input)
    if user_text is None:
        return _fallback_response()

    semaphore: asyncio.Semaphore = request.app.state.chatbot_semaphore
    acquired = False
    try:
        # Avoid queueing behind slow catalog connections; Zalo needs a response
        # within two seconds, and fallback is preferable to a failed flow.
        await asyncio.wait_for(semaphore.acquire(), timeout=0.01)
        acquired = True
        async with asyncio.timeout(settings.zalo_chatbot_timeout_seconds):
            response = await _search_response(request, user_text)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=render_dynamic_response(
                response,
                layout=settings.zalo_chatbot_layout,
                image_urls=_generic_image_urls(settings, response),
            ),
            headers={"Cache-Control": "no-store"},
        )
    except (TimeoutError, CatalogUnavailableError):
        return _fallback_response()
    except Exception:
        # Do not expose messages, user input, catalog details, or secrets to
        # Zalo.  The payload must remain valid even for a transient error.
        return _fallback_response()
    finally:
        if acquired:
            semaphore.release()
