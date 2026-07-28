from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/zalo")
async def receive_zalo_webhook() -> JSONResponse:
    """Acknowledge the Zalo callback without retaining or processing its payload.

    Zalo validates a registered callback by issuing an HTTP POST and requires a
    200 response.  Event handling remains intentionally disabled until the
    signed-payload contract has been verified and configured.
    """
    # Do not parse, log, persist, or act on the incoming payload here.  The
    # eventual implementation must verify the provider signature, deduplicate
    # events, and enqueue a job before any user-facing action.
    return JSONResponse(
        status_code=200,
        content={
            "code": "ZALO_WEBHOOK_ACKNOWLEDGED",
            "detail": "Webhook đã được xác nhận; xử lý sự kiện đang tắt cho tới khi xác minh chữ ký Zalo OA.",
        },
    )
