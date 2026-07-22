from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/live", response_model=HealthStatus)
async def liveness() -> HealthStatus:
    """Báo tiến trình API còn sống mà không gọi dependency bên ngoài."""
    return HealthStatus()


@router.get("/ready", response_model=HealthStatus)
async def readiness() -> HealthStatus:
    """Trả trạng thái readiness tối thiểu của scaffold."""
    # TODO: Kiểm tra Redis và các provider bắt buộc trước khi dùng ở production.
    return HealthStatus()
