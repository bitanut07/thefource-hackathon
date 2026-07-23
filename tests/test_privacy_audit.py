import asyncio
import hashlib
import hmac
from typing import cast

import pytest

from domain.audit import AuditService, InMemoryAuditService, QueryAudit
from domain.privacy import (
    RECURSIVE_VALUE,
    REDACTED_VALUE,
    hash_user_id,
    redact_mapping,
)


def test_hash_user_id_uses_hmac_sha256() -> None:
    user_id = "user-123"
    salt = "local-audit-salt"
    expected = hmac.new(
        salt.encode("utf-8"),
        user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert hash_user_id(user_id, salt) == expected
    assert len(hash_user_id(user_id, salt)) == 64


def test_hash_user_id_requires_a_non_empty_salt() -> None:
    with pytest.raises(ValueError, match="salt must not be empty"):
        hash_user_id("user-123", "")


def test_redact_mapping_handles_nested_containers_case_insensitively() -> None:
    value: dict[str, object] = {
        "Authorization": "Bearer raw-token",
        "profile": {
            "display_name": "An",
            "accessToken": "secret-token",
            "preferences": [
                {"COOKIE": "session-cookie", "theme": "dark"},
                ("safe", {"db_PASSWORD_hash": "password-hash"}),
            ],
        },
    }

    result = redact_mapping(value)

    assert result == {
        "Authorization": REDACTED_VALUE,
        "profile": {
            "display_name": "An",
            "accessToken": REDACTED_VALUE,
            "preferences": [
                {"COOKIE": REDACTED_VALUE, "theme": "dark"},
                ("safe", {"db_PASSWORD_hash": REDACTED_VALUE}),
            ],
        },
    }
    assert cast(dict[str, object], value["profile"])["accessToken"] == "secret-token"


def test_redact_mapping_stops_recursive_containers() -> None:
    recursive_list: list[object] = []
    recursive_list.append(recursive_list)

    assert redact_mapping({"items": recursive_list}) == {"items": [RECURSIVE_VALUE]}


def test_audit_service_records_immutable_snapshots_in_order() -> None:
    service = AuditService()
    first = QueryAudit(event_id="event-1", user_hash="hash-1")
    second = QueryAudit(event_id="event-2", detected_intent="lookup")

    asyncio.run(service.record(first))
    snapshot = service.entries
    asyncio.run(service.record(second))

    assert snapshot == (first,)
    assert service.entries == (first, second)


def test_explicit_in_memory_audit_service_preserves_contract() -> None:
    service = InMemoryAuditService()
    entry = QueryAudit(event_id="event-1")

    asyncio.run(service.record(entry))

    assert service.entries == (entry,)
