import unicodedata
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Security, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from api.security import require_api_key
from domain.models import RegistryService, ServiceCategory, ServiceType
from domain.registry import ServiceRegistryRepository
from domain.search import LaunchUrlPolicy

router = APIRouter(
    prefix="/api/v1/services",
    tags=["Service Registry"],
    dependencies=[Security(require_api_key)],
)


class ServiceIntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    example_query: str


class RegistryServiceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    name: str
    provider: str
    service_type: ServiceType
    category: ServiceCategory
    description: str
    launch_url: HttpUrl
    avatar_url: HttpUrl | None = None
    region: str | None = None
    target_user: str | None = None
    organization: str | None = None
    aliases: list[str] = Field(default_factory=list)
    intents: list[ServiceIntentView] = Field(default_factory=list)
    last_verified_at: datetime


class RegistryServiceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    offset: int
    limit: int
    items: list[RegistryServiceView]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_marks).split())


def _to_view(service: RegistryService) -> RegistryServiceView:
    if service.last_verified_at is None:
        raise ValueError("active registry service is missing last_verified_at")
    return RegistryServiceView(
        service_id=service.id,
        name=service.name,
        provider=service.provider,
        service_type=service.service_type,
        category=service.category,
        description=service.description,
        launch_url=HttpUrl(service.launch_url),
        avatar_url=HttpUrl(service.avatar_url) if service.avatar_url else None,
        region=service.region,
        target_user=service.target_user,
        organization=service.organization,
        aliases=list(service.aliases),
        intents=[
            ServiceIntentView(
                intent=intent.intent,
                example_query=intent.example_query,
            )
            for intent in service.intents
        ],
        last_verified_at=service.last_verified_at,
    )


def _matches_query(service: RegistryService, query: str) -> bool:
    normalized_query = _normalize(query)
    if not normalized_query:
        return True
    text = " ".join(
        (
            service.name,
            service.provider,
            service.description,
            service.region or "",
            service.target_user or "",
            service.organization or "",
            *service.aliases,
            *(intent.intent for intent in service.intents),
            *(intent.example_query for intent in service.intents),
        )
    )
    return normalized_query in _normalize(text)


@router.get(
    "",
    response_model=RegistryServiceListResponse,
    summary="Liệt kê dịch vụ runtime đã được review",
    description=(
        "Chỉ trả record active có launch URL vượt qua allowlist. Không trả "
        "candidate nghiên cứu hoặc điểm ranking nội bộ."
    ),
)
async def list_services(
    request: Request,
    q: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=160,
            description="Tìm theo tên, mô tả, alias hoặc intent.",
        ),
    ] = None,
    category: ServiceCategory | None = None,
    service_type: ServiceType | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RegistryServiceListResponse:
    registry = cast(ServiceRegistryRepository, request.app.state.registry)
    active_services = await registry.list_active()
    url_policy = cast(LaunchUrlPolicy, request.app.state.launch_url_policy)
    services = [
        service
        for service in active_services
        if url_policy.is_allowed_for_service(service.service_type, service.launch_url)
        and (category is None or service.category == category)
        and (service_type is None or service.service_type == service_type)
        and (q is None or _matches_query(service, q))
    ]
    services.sort(key=lambda service: (_normalize(service.name), str(service.id)))
    return RegistryServiceListResponse(
        total=len(services),
        offset=offset,
        limit=limit,
        items=[_to_view(service) for service in services[offset : offset + limit]],
    )


@router.get(
    "/{service_id}",
    response_model=RegistryServiceView,
    summary="Xem chi tiết một dịch vụ runtime",
    responses={404: {"description": "Service không active hoặc URL bị policy chặn."}},
)
async def get_service(service_id: UUID, request: Request) -> RegistryServiceView:
    registry = cast(ServiceRegistryRepository, request.app.state.registry)
    url_policy = cast(LaunchUrlPolicy, request.app.state.launch_url_policy)
    service = await registry.get_active(service_id)
    if service is None or not url_policy.is_allowed_for_service(
        service.service_type,
        service.launch_url,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy dịch vụ đang hoạt động.",
        )
    return _to_view(service)
