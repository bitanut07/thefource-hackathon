"""Verified Zalo OA webhook and consultation-message client."""

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

import httpx

from config import Settings


class ZaloConfigurationError(RuntimeError):
    """Raised when a required Zalo OA credential has not been configured."""


class ZaloAPIError(RuntimeError):
    """Raised when Zalo refuses a consultation message."""


class ConfiguredZaloClient:
    """Verify signed OA events and send text replies through the OA API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_base_url = (settings.zalo_api_base_url or "https://openapi.zalo.me").rstrip("/")

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Verify ``sha256(appId + rawData + timestamp + OAsecretKey)``.

        The exact raw JSON bytes received from Zalo are preserved for the MAC;
        re-serializing parsed JSON would change its signature.
        """

        secret = self._secret_value(self._settings.zalo_webhook_secret)
        if not secret:
            raise ZaloConfigurationError("ZALO_WEBHOOK_SECRET is not configured")

        signature = headers.get("x-zevent-signature", "").strip()
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

        access_token = self._secret_value(self._settings.zalo_access_token)
        if not access_token:
            raise ZaloConfigurationError("ZALO_ACCESS_TOKEN is not configured")
        normalized_text = text.strip()
        if not user_id or not normalized_text:
            raise ValueError("user_id and text are required")
        if len(normalized_text) > 2_000:
            normalized_text = normalized_text[:1_997].rstrip() + "..."

        async with httpx.AsyncClient(base_url=self._api_base_url, timeout=10.0) as client:
            response = await client.post(
                "/v3.0/oa/message/cs",
                headers={"access_token": access_token},
                json={"recipient": {"user_id": user_id}, "message": {"text": normalized_text}},
            )
        try:
            payload: Any = response.json()
        except json.JSONDecodeError as exc:
            raise ZaloAPIError("Zalo returned a non-JSON response") from exc
        if response.is_error or not isinstance(payload, dict) or payload.get("error") != 0:
            raise ZaloAPIError("Zalo rejected the consultation message")

    @staticmethod
    def _secret_value(value: Any) -> str:
        return value.get_secret_value().strip() if value is not None else ""
