"""Short-lived, hashed-key conversation context for Zalo replies."""

import hashlib
import json
from typing import Any, cast

from redis import Redis


class ConversationStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int = 1_800) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    def history(self, user_id: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        values = cast(list[Any], self._redis.lrange(self._key(user_id), 0, -1))
        for raw in values:
            try:
                item = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not (
                isinstance(item, dict)
                and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("text"), str)
            ):
                continue
            entries.append({"role": item["role"], "text": item["text"][:2_000]})
        return entries

    def append(self, user_id: str, role: str, text: str) -> None:
        key = self._key(user_id)
        self._redis.rpush(key, json.dumps({"role": role, "text": text[:2_000]}, ensure_ascii=False))
        self._redis.ltrim(key, -10, -1)
        self._redis.expire(key, self._ttl_seconds)

    @staticmethod
    def _key(user_id: str) -> str:
        return "zalo:conversation:" + hashlib.sha256(user_id.encode()).hexdigest()
