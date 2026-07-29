"""Verified Zalo OA webhook and consultation-message client."""

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from redis import Redis
from redis.exceptions import RedisError

from config import Settings


class ZaloConfigurationError(RuntimeError):
    """Raised when a required Zalo OA credential has not been configured."""


class ZaloAPIError(RuntimeError):
    """Raised when Zalo refuses a consultation message."""


@dataclass(frozen=True)
class ZaloTokens:
    """The current OA token pair, never emitted to logs or API responses."""

    access_token: str
    refresh_token: str


class ZaloTokenStore(Protocol):
    """Minimal persistence contract so refreshed tokens survive a worker restart."""

    def load(self, key: str, seed_digest: str) -> ZaloTokens | None: ...

    def save(self, key: str, seed_digest: str, tokens: ZaloTokens) -> None: ...


class RedisZaloTokenStore:
    """Persist rotating OA tokens outside the container image.

    ``seed_digest`` identifies the refresh token supplied through deployment env.
    If an operator replaces that env value, an older Redis record is ignored.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url)

    def load(self, key: str, seed_digest: str) -> ZaloTokens | None:
        try:
            raw = self._redis.get(key)
        except RedisError:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if not isinstance(raw, str):
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or payload.get("seed_digest") != seed_digest:
            return None
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            return None
        if not access_token.strip() or not refresh_token.strip():
            return None
        return ZaloTokens(access_token=access_token.strip(), refresh_token=refresh_token.strip())

    def save(self, key: str, seed_digest: str, tokens: ZaloTokens) -> None:
        payload = {
            "seed_digest": seed_digest,
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
        }
        try:
            self._redis.set(key, json.dumps(payload, separators=(",", ":")))
        except RedisError:
            # Sending a reply must not fail merely because token persistence is down.
            return


class ConfiguredZaloClient:
    """Verify signed OA events and send text replies through the OA API."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        token_store: ZaloTokenStore | None = None,
    ) -> None:
        self._settings = settings
        self._api_base_url = (settings.zalo_api_base_url or "https://openapi.zalo.me").rstrip("/")
        self._transport = transport
        self._token_store = token_store or RedisZaloTokenStore(settings.redis_url)

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Verify ``sha256(appId + rawData + timestamp + OAsecretKey)``.

        The exact raw JSON bytes received from Zalo are preserved for the MAC;
        re-serializing parsed JSON would change its signature.
        """

        secret = self._secret_value(self._settings.zalo_webhook_secret)
        if not secret:
            raise ZaloConfigurationError("ZALO_WEBHOOK_SECRET is not configured")

        signature = headers.get("x-zevent-signature", "").strip()
        if signature.casefold().startswith("mac="):
            signature = signature[4:].strip()
        if not signature:
            return False
        try:
            body = json.loads(raw_body)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(body, dict):
            return False
        app_id = body.get("app_id")
        timestamp = body.get("timestamp")
        if not isinstance(app_id, str) or not isinstance(timestamp, str):
            return False

        signed_data = app_id.encode() + raw_body + timestamp.encode() + secret.encode()
        expected = hashlib.sha256(signed_data).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def send_text(self, user_id: str, text: str) -> None:
        """Send a consultation text message, limited to Zalo's 2,000 chars."""

        normalized_text = text.strip()
        if not user_id or not normalized_text:
            raise ValueError("user_id and text are required")
        if len(normalized_text) > 2_000:
            normalized_text = normalized_text[:1_997].rstrip() + "..."

        tokens, seed_digest, cache_key = self._current_tokens()
        response, payload = await self._send_consultation_message(
            user_id, normalized_text, tokens.access_token
        )
        if self._is_expired_access_token(payload):
            tokens = await self._refresh_tokens(tokens, seed_digest, cache_key)
            response, payload = await self._send_consultation_message(
                user_id, normalized_text, tokens.access_token
            )
        if response.is_error or not isinstance(payload, dict) or payload.get("error") != 0:
            raise ZaloAPIError(self._api_error_message(response, payload))

    def _current_tokens(self) -> tuple[ZaloTokens, str, str]:
        access_token = self._secret_value(self._settings.zalo_access_token)
        refresh_token = self._secret_value(self._settings.zalo_refresh_token)
        if not access_token:
            raise ZaloConfigurationError("ZALO_ACCESS_TOKEN is not configured")
        if not refresh_token:
            raise ZaloConfigurationError("ZALO_REFRESH_TOKEN is not configured")
        seed_digest = hashlib.sha256(refresh_token.encode()).hexdigest()
        identity = self._settings.zalo_oa_id or self._settings.zalo_app_id or "default"
        cache_key = f"zalo:oa:tokens:{identity}"
        tokens = self._token_store.load(cache_key, seed_digest) or ZaloTokens(
            access_token, refresh_token
        )
        return tokens, seed_digest, cache_key

    async def _send_consultation_message(
        self, user_id: str, text: str, access_token: str
    ) -> tuple[httpx.Response, Any]:
        async with httpx.AsyncClient(
            base_url=self._api_base_url, timeout=10.0, transport=self._transport
        ) as client:
            response = await client.post(
                "/v3.0/oa/message/cs",
                headers={"access_token": access_token},
                json={"recipient": {"user_id": user_id}, "message": {"text": text}},
            )
        return response, self._json_payload(response)

    async def _refresh_tokens(
        self, tokens: ZaloTokens, seed_digest: str, cache_key: str
    ) -> ZaloTokens:
        app_id = self._settings.zalo_app_id.strip()
        app_secret = self._secret_value(self._settings.zalo_app_secret)
        if not app_id or not app_secret:
            raise ZaloConfigurationError(
                "ZALO_APP_ID and ZALO_APP_SECRET are required to refresh an expired OA access token"
            )
        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            response = await client.post(
                "https://oauth.zaloapp.com/v4/oa/access_token",
                headers={"secret_key": app_secret},
                data={
                    "app_id": app_id,
                    "refresh_token": tokens.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        payload = self._json_payload(response)
        refresh_failed = (
            response.is_error
            or not isinstance(payload, dict)
            or payload.get("error") not in (None, 0)
        )
        if refresh_failed:
            raise ZaloAPIError(
                self._api_error_message(response, payload, operation="refresh OA token")
            )
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise ZaloAPIError("Zalo refresh response did not contain a new OA token pair")
        refreshed = ZaloTokens(
            access_token=access_token.strip(), refresh_token=refresh_token.strip()
        )
        if not refreshed.access_token or not refreshed.refresh_token:
            raise ZaloAPIError("Zalo refresh response contained an empty OA token")
        self._token_store.save(cache_key, seed_digest, refreshed)
        return refreshed

    @staticmethod
    def _json_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _is_expired_access_token(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("error") == -216:
            return True
        message = payload.get("message")
        return isinstance(message, str) and "access token has expired" in message.casefold()

    @staticmethod
    def _api_error_message(
        response: httpx.Response, payload: Any, *, operation: str = "send OA message"
    ) -> str:
        error_code = payload.get("error") if isinstance(payload, dict) else None
        return f"Zalo rejected {operation} (HTTP {response.status_code}, error {error_code!r})"

    @staticmethod
    def _secret_value(value: Any) -> str:
        return value.get_secret_value().strip() if value is not None else ""
