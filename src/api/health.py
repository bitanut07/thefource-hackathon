from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

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
