from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request, Security, status
from pydantic import BaseModel, ConfigDict, Field

from api.security import require_api_key
from config import Settings
from domain.rag_store import SqliteRagStore
from skills.factory import parse_allowed_hosts

router = APIRouter(
    prefix="/api/v1/research",
    tags=["RAG research"],
    dependencies=[Security(require_api_key)],
)


class ResearchSearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "text": "nhân viên VNG mua đồ ăn Ba Sao",
                    "limit": 5,
                },
                {
                    "text": "quán nước VNG Campus",
                    "category": "shopping",
                    "limit": 5,
                },
            ]
        },
    )

    text: str = Field(min_length=1, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    limit: int = Field(default=8, ge=1, le=10)
    launchable_only: bool = False


class ResearchSearchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    document_id: str
    name: str
    category: str | None = None
    channel_type: str | None = None
    source_type: str
    review_status: str
    verification_status: str
    launchable: bool
    matched_terms: list[str]
    usage: Literal["research_only"] = "research_only"


class ResearchSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    total: int
    items: list[ResearchSearchItem]
    warning: str = (
        "Kết quả chỉ dùng để nghiên cứu/review; không phải Service Registry "
        "và không được dùng làm CTA."
    )


def _database_path(settings: Settings) -> Path:
    return settings.rag_data_path


@router.post(
    "/search",
    response_model=ResearchSearchResponse,
    summary="Tìm trong kho RAG nghiên cứu",
    description=(
        "Trả provenance/trạng thái review để kiểm tra dữ liệu crawl. Endpoint "
        "không trả URL, metadata thô hoặc source path và không kích hoạt record."
    ),
    responses={
        503: {"description": ("SQLite RAG chưa được build; chạy scripts/build_rag_db.py trước.")}
    },
)
def search_research(
    payload: ResearchSearchRequest,
    request: Request,
) -> ResearchSearchResponse:
    settings = cast(Settings, request.app.state.settings)
    database_path = _database_path(settings)
    if not database_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kho RAG chưa được build.",
        )

    with SqliteRagStore(
        database_path,
        allowed_launch_hosts=parse_allowed_hosts(settings.allowed_launch_hosts),
    ) as store:
        raw_results = store.search(
            payload.text,
            limit=payload.limit,
            launchable_only=payload.launchable_only,
            category=payload.category,
        )

    return ResearchSearchResponse(
        query=payload.text,
        total=len(raw_results),
        items=[
            ResearchSearchItem(
                rank=rank,
                document_id=result.document.document_id,
                name=result.document.name,
                category=result.document.category,
                channel_type=result.document.channel_type,
                source_type=result.document.source_type,
                review_status=result.document.review_status,
                verification_status=result.document.verification_status,
                launchable=result.document.launchable,
                matched_terms=list(result.matched_terms),
            )
            for rank, result in enumerate(raw_results, start=1)
        ],
    )
