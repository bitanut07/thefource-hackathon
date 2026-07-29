"""Shared-account authentication for the catalog review console.

The console authorizes catalog *writes*, so it uses its own credential instead of
``NAVIGATOR_API_KEY``.  Sessions are opaque random tokens held in Redis: that
gives real server-side revocation and an expiry the client cannot extend, which a
self-signed stateless token would not.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Request, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from redis import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from config import Settings

MIN_ADMIN_PASSWORD_LENGTH = 12
ADMIN_ACTOR = "admin"
_SESSION_KEY_PREFIX = "admin:session:"
_LOGIN_ATTEMPT_KEY_PREFIX = "admin:login-attempts:"

admin_bearer = HTTPBearer(
    scheme_name="AdminSession",
    description="Token trả về từ POST /api/v1/admin/session.",
    auto_error=False,
)


def configured_admin_password(settings: Settings) -> str:
    """Return the review-console password only when it meets the safety floor.

    A short shared secret is treated as absent rather than accepted, so a weak
    value fails closed with 503 instead of quietly guarding catalog writes.
    """

    value = (
        settings.admin_password.get_secret_value().strip()
        if settings.admin_password is not None
        else ""
    )
    return value if len(value) >= MIN_ADMIN_PASSWORD_LENGTH else ""


def _token_digest(token: str) -> str:
    """Hash a session token before it is used as a Redis key.

    Storing only the digest means a leaked Redis snapshot cannot be replayed as a
    live session.
    """

    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AdminSession:
    token: str
    actor: str
    expires_at: datetime


class AdminSessionStore:
    """Issue, resolve and revoke review-console sessions in Redis."""

    def __init__(self, connection: Redis, *, ttl_seconds: int) -> None:
        self._connection = connection
        self._ttl_seconds = ttl_seconds

    async def issue(self, actor: str = ADMIN_ACTOR) -> AdminSession:
        token = secrets.token_urlsafe(32)
        key = f"{_SESSION_KEY_PREFIX}{_token_digest(token)}"
        await run_in_threadpool(self._connection.set, key, actor, ex=self._ttl_seconds)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._ttl_seconds)
        return AdminSession(token=token, actor=actor, expires_at=expires_at)

    async def resolve(self, token: str) -> str | None:
        if not token.strip():
            return None
        key = f"{_SESSION_KEY_PREFIX}{_token_digest(token)}"
        actor = await run_in_threadpool(self._connection.get, key)
        if actor is None:
            return None
        return actor.decode() if isinstance(actor, bytes) else str(actor)

    async def revoke(self, token: str) -> None:
        if not token.strip():
            return
        key = f"{_SESSION_KEY_PREFIX}{_token_digest(token)}"
        await run_in_threadpool(self._connection.delete, key)

    async def register_failed_attempt(self, client_key: str, *, window_seconds: int) -> int:
        """Count a failed login and return the number within the current window."""

        key = f"{_LOGIN_ATTEMPT_KEY_PREFIX}{client_key}"
        attempts = await run_in_threadpool(self._connection.incr, key)
        count = int(cast(int, attempts))
        if count == 1:
            await run_in_threadpool(self._connection.expire, key, window_seconds)
        return count

    async def failed_attempts(self, client_key: str) -> int:
        key = f"{_LOGIN_ATTEMPT_KEY_PREFIX}{client_key}"
        value = await run_in_threadpool(self._connection.get, key)
        if value is None:
            return 0
        try:
            return int(cast(bytes | str, value))
        except (TypeError, ValueError):
            return 0

    async def clear_failed_attempts(self, client_key: str) -> None:
        key = f"{_LOGIN_ATTEMPT_KEY_PREFIX}{client_key}"
        await run_in_threadpool(self._connection.delete, key)


def _client_key(request: Request) -> str:
    """Identify the caller for login throttling.

    ``request.client`` is the direct peer, so behind a reverse proxy every login
    shares one bucket and the limit becomes global.  Forwarded headers are not
    trusted here because they are caller-supplied and would let an attacker mint a
    fresh bucket per attempt, which is strictly worse than a shared one.
    """

    client = request.client
    return client.host if client is not None else "unknown"


def _session_store(request: Request) -> AdminSessionStore:
    return cast(AdminSessionStore, request.app.state.admin_session_store)


async def require_admin_session(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(admin_bearer)] = None,
) -> str:
    """Authenticate a console request and return the actor for audit records."""

    settings = cast(Settings, request.app.state.settings)
    if not configured_admin_password(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Review console chưa được cấu hình ADMIN_PASSWORD "
                f"(tối thiểu {MIN_ADMIN_PASSWORD_LENGTH} ký tự)."
            ),
        )
    if credentials is None or credentials.scheme.strip().casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cần session token của review console.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        actor = await _session_store(request).resolve(credentials.credentials)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không kiểm tra được session vì Redis chưa sẵn sàng.",
        ) from exc
    if actor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return actor


router = APIRouter(prefix="/api/v1/admin", tags=["Review Console"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    actor: str
    expires_at: datetime


@router.post(
    "/session",
    response_model=LoginResponse,
    summary="Đăng nhập review console",
    description=(
        "Đổi ADMIN_PASSWORD lấy session token dùng cho các API quản trị. "
        "Token nên được giữ ở phía server của app quản trị, không lưu trong "
        "localStorage của trình duyệt."
    ),
    responses={
        401: {"description": "Mật khẩu không đúng."},
        429: {"description": "Quá nhiều lần đăng nhập sai."},
        503: {"description": "ADMIN_PASSWORD chưa cấu hình hoặc Redis chưa sẵn sàng."},
    },
)
async def create_session(request: Request, payload: LoginRequest) -> LoginResponse:
    settings = cast(Settings, request.app.state.settings)
    configured_password = configured_admin_password(settings)
    if not configured_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Review console chưa được cấu hình ADMIN_PASSWORD "
                f"(tối thiểu {MIN_ADMIN_PASSWORD_LENGTH} ký tự)."
            ),
        )

    store = _session_store(request)
    client_key = _client_key(request)
    try:
        attempts = await store.failed_attempts(client_key)
        if attempts >= settings.admin_login_max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Đăng nhập sai quá nhiều lần; thử lại sau.",
                headers={"Retry-After": str(settings.admin_login_attempt_window_seconds)},
            )
        if not secrets.compare_digest(payload.password, configured_password):
            await store.register_failed_attempt(
                client_key,
                window_seconds=settings.admin_login_attempt_window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mật khẩu không đúng.",
            )
        await store.clear_failed_attempts(client_key)
        session = await store.issue()
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không tạo được session vì Redis chưa sẵn sàng.",
        ) from exc
    return LoginResponse(
        token=session.token,
        actor=session.actor,
        expires_at=session.expires_at,
    )


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Đăng xuất review console",
    description="Thu hồi session token ngay tại server.",
)
async def delete_session(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(admin_bearer)] = None,
    _actor: Annotated[str, Security(require_admin_session)] = ADMIN_ACTOR,
) -> Response:
    if credentials is not None:
        try:
            await _session_store(request).revoke(credentials.credentials)
        except RedisError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Không thu hồi được session vì Redis chưa sẵn sàng.",
            ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
