from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/zalo")
async def receive_zalo_webhook() -> JSONResponse:
    """Chặn webhook cho tới khi contract Zalo OA được xác minh."""
    # TODO: Xác minh chữ ký, chuẩn hóa event, chống trùng và đưa job vào hàng đợi.
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "code": "ZALO_CONTRACT_NOT_CONFIGURED",
            "detail": "Cần xác minh contract webhook Zalo OA trước khi bật endpoint này.",
        },
    )
