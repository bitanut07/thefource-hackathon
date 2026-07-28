from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from api.security import configured_navigator_api_key
from config import Settings
from domain.postgres_registry import CatalogUnavailableError
from domain.registry import ServiceRegistryRepository
from domain.search import LaunchUrlPolicy

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/live", response_model=HealthStatus)
async def liveness() -> HealthStatus:
    """Báo tiến trình API còn sống mà không gọi dependency bên ngoài."""
    return HealthStatus()


@router.get("/ready", response_model=HealthStatus)
async def readiness(request: Request) -> HealthStatus:
    """Check the dependency required by the API and RQ worker."""
    settings = cast(Settings, request.app.state.settings)
    api_key = (
        settings.gemini_api_key.get_secret_value().strip()
        if settings.gemini_api_key is not None
        else ""
    )
    if settings.llm_provider.strip().casefold() != "gemini" or not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini chưa được cấu hình.",
        )

    navigator_api_key = configured_navigator_api_key(settings)
    if not navigator_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Khóa truy cập Navigator API chưa được cấu hình.",
        )

    registry = cast(ServiceRegistryRepository, request.app.state.registry)
    url_policy = cast(LaunchUrlPolicy, request.app.state.launch_url_policy)
    try:
        active_services = await registry.list_active()
    except CatalogUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service Catalog PostgreSQL chưa sẵn sàng.",
        ) from exc
    if not active_services:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service Registry không có dịch vụ đang hoạt động.",
        )
    if any(
        not url_policy.is_allowed_for_service(service.service_type, service.launch_url)
        for service in active_services
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Allowlist URL chưa bao phủ Service Registry đang hoạt động.",
        )

    connection = cast(Redis, request.app.state.redis_connection)
    try:
        redis_ready = await run_in_threadpool(connection.ping)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis chưa sẵn sàng.",
        ) from exc
    if not redis_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis chưa sẵn sàng.",
        )
    return HealthStatus()
