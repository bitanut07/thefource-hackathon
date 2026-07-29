"""Inbound Zalo OA webhook endpoint.

The endpoint only authenticates and queues supported text events, so it always
returns within Zalo's two-second webhook deadline.
"""

import hashlib
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from rq import Queue

from config import Settings
from zalo.client import ConfiguredZaloClient, ZaloConfigurationError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_DEDUP_TTL_SECONDS = 86_400
logger = logging.getLogger(__name__)


def _text_event(payload: object) -> tuple[str, str, str] | None:
    if not isinstance(payload, dict) or payload.get("event_name") != "user_send_text":
        return None
    sender = payload.get("sender")
    message = payload.get("message")
    if not isinstance(sender, dict) or not isinstance(message, dict):
        return None
    user_id, text, message_id = sender.get("id"), message.get("text"), message.get("msg_id")
    if not (
        isinstance(user_id, str)
        and isinstance(text, str)
        and isinstance(message_id, str)
        and user_id.strip()
        and text.strip()
        and message_id.strip()
    ):
        return None
    return user_id.strip(), text.strip(), message_id.strip()


def _event_key(message_id: str) -> str:
    """Avoid retaining a raw Zalo message id as a Redis key."""

    return hashlib.sha256(message_id.encode()).hexdigest()


def _is_zalo_console_sample(payload: object) -> bool:
    """Recognize Zalo's fixed, unsigned console test fixture.

    The Developer Console's *Test* button submits this published example
    without ``X-ZEvent-Signature``.  It is acknowledged but never queued, so
    matching it cannot trigger a message or bypass verification for live data.
    """

    if not isinstance(payload, dict) or payload.get("event_name") != "user_send_text":
        return False
    message = payload.get("message")
    return isinstance(message, dict) and (
        message.get("msg_id") == "This is message id"
        and message.get("text") == "This is testing message"
    )


@router.post("/zalo")
async def receive_zalo_webhook(request: Request) -> JSONResponse:
    """Authenticate Zalo text events, deduplicate them, and enqueue work."""

    raw_body = await request.body()
    try:
        payload: Any = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": "INVALID_JSON"},
        )

    event = _text_event(payload)
    if event is None:
        # Unsupported events are intentionally acknowledged; Zalo requires 200
        # and retrying them cannot make this service handle them.
        return JSONResponse(status_code=200, content={"code": "ZALO_EVENT_IGNORED"})
    if _is_zalo_console_sample(payload):
        return JSONResponse(status_code=200, content={"code": "ZALO_CONSOLE_TEST_ACKNOWLEDGED"})

    settings = cast(Settings, request.app.state.settings)
    client = ConfiguredZaloClient(settings)
    try:
        verified = client.verify(raw_body, request.headers)
    except ZaloConfigurationError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"code": "ZALO_NOT_CONFIGURED"},
        )
    if not verified:
        signature_headers = sorted(
            key for key in request.headers.keys() if "signature" in key.casefold()
        )
        logger.warning(
            "Rejected Zalo webhook signature; signature_headers=%s",
            signature_headers,
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "INVALID_SIGNATURE"},
        )

    user_id, text, message_id = event
    event_hash = _event_key(message_id)
    redis = request.app.state.redis_connection
    if not redis.set(f"zalo:webhook:{event_hash}", "1", nx=True, ex=_DEDUP_TTL_SECONDS):
        return JSONResponse(status_code=200, content={"code": "ZALO_EVENT_DUPLICATE"})

    queue = cast(Queue, request.app.state.queue)
    try:
        queue.enqueue(
            "worker.jobs.process_zalo_text_event",
            user_id,
            text,
            message_id,
            job_id=f"zalo-{event_hash}",
            result_ttl=0,
            failure_ttl=_DEDUP_TTL_SECONDS,
        )
    except Exception:
        redis.delete(f"zalo:webhook:{event_hash}")
        raise
    return JSONResponse(status_code=200, content={"code": "ZALO_EVENT_QUEUED"})
