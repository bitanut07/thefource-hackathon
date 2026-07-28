import hashlib
import json

from pydantic import SecretStr

from config import Settings
from zalo.client import ConfiguredZaloClient


def test_zalo_signature_uses_exact_raw_body_and_secret() -> None:
    settings = Settings(zalo_webhook_secret=SecretStr("test-oa-secret"))
    body = json.dumps(
        {"app_id": "app-1", "timestamp": "123", "event_name": "user_send_text"},
        separators=(",", ":"),
    ).encode()
    signature = hashlib.sha256(b"app-1" + body + b"123" + b"test-oa-secret").hexdigest()

    assert ConfiguredZaloClient(settings).verify(body, {"x-zevent-signature": signature})
    assert ConfiguredZaloClient(settings).verify(body, {"x-zevent-signature": f"mac={signature}"})
    assert not ConfiguredZaloClient(settings).verify(body, {"x-zevent-signature": "bad"})
