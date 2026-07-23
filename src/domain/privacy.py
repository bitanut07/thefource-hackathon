import hashlib
import hmac
from collections.abc import Mapping
from typing import cast

SENSITIVE_KEY_PARTS = ("authorization", "cookie", "secret", "token", "password")
REDACTED_VALUE = "[REDACTED]"
RECURSIVE_VALUE = "[RECURSIVE]"


def hash_user_id(user_id: str, salt: str) -> str:
    """Return a stable HMAC-SHA256 digest suitable for audit correlation."""
    if not salt:
        raise ValueError("salt must not be empty")

    return hmac.new(
        salt.encode("utf-8"),
        user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def redact_mapping(value: Mapping[str, object]) -> dict[str, object]:
    """Return a recursively redacted copy that is safe to pass to a logger."""
    return _redact_str_mapping(value, active_container_ids=set())


def _redact_str_mapping(
    value: Mapping[str, object],
    *,
    active_container_ids: set[int],
) -> dict[str, object]:
    container_id = id(value)
    if container_id in active_container_ids:
        return {"recursive": RECURSIVE_VALUE}

    active_container_ids.add(container_id)
    try:
        return {
            key: (
                REDACTED_VALUE
                if _is_sensitive_key(key)
                else _redact_value(item, active_container_ids=active_container_ids)
            )
            for key, item in value.items()
        }
    finally:
        active_container_ids.remove(container_id)


def _redact_value(value: object, *, active_container_ids: set[int]) -> object:
    if isinstance(value, Mapping):
        container_id = id(value)
        if container_id in active_container_ids:
            return RECURSIVE_VALUE

        active_container_ids.add(container_id)
        try:
            mapping = cast(Mapping[object, object], value)
            return {
                key: (
                    REDACTED_VALUE
                    if isinstance(key, str) and _is_sensitive_key(key)
                    else _redact_value(item, active_container_ids=active_container_ids)
                )
                for key, item in mapping.items()
            }
        finally:
            active_container_ids.remove(container_id)

    if isinstance(value, list):
        container_id = id(value)
        if container_id in active_container_ids:
            return RECURSIVE_VALUE

        active_container_ids.add(container_id)
        try:
            return [
                _redact_value(item, active_container_ids=active_container_ids) for item in value
            ]
        finally:
            active_container_ids.remove(container_id)

    if isinstance(value, tuple):
        container_id = id(value)
        if container_id in active_container_ids:
            return RECURSIVE_VALUE

        active_container_ids.add(container_id)
        try:
            return tuple(
                _redact_value(item, active_container_ids=active_container_ids) for item in value
            )
        finally:
            active_container_ids.remove(container_id)

    return value


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.casefold()
    return any(part in normalized_key for part in SENSITIVE_KEY_PARTS)
