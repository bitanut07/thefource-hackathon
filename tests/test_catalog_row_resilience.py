"""One unusable catalog row must not take the whole assistant down.

``_row_to_service`` coerces ``category`` and ``service_type`` through their enums, so
a row holding a value outside them raises ``ValueError`` — which is not a
``psycopg.Error`` and used to escape as an unhandled 500 on every navigation request.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from domain.models import ServiceCategory, ServiceType
from domain.postgres_registry import PostgresServiceRegistry

GOOD_ID = UUID("00000000-0000-4000-8000-000000000001")
BAD_ID = UUID("00000000-0000-4000-8000-000000000002")


def _row(service_id: UUID, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": service_id,
        "name": "Dịch vụ",
        "provider": "Đơn vị",
        "service_type": ServiceType.OA.value,
        "category": ServiceCategory.UTILITIES.value,
        "description": "Mô tả.",
        "launch_url": "https://zalo.me/1234567890123456789",
        "owner": "review-console",
        "active": True,
        "service_priority": 10,
        "region": None,
        "target_user": None,
        "organization": None,
        "last_verified_at": datetime(2026, 7, 29, tzinfo=UTC),
        "aliases": [],
        "intents": [],
    }
    row.update(overrides)
    return row


def test_a_row_with_an_off_enum_category_is_skipped_not_fatal(
    caplog: object,
) -> None:
    rows = [_row(GOOD_ID), _row(BAD_ID, category="uncategorized")]

    with _capture(caplog) as records:
        services = PostgresServiceRegistry._rows_to_services(rows)

    # The healthy row still reaches the assistant.
    assert [service.id for service in services] == [GOOD_ID]
    # And the cause is logged with the offending id so it can be fixed.
    assert any(str(BAD_ID) in record.getMessage() for record in records)


def test_an_off_enum_service_type_is_skipped_too() -> None:
    services = PostgresServiceRegistry._rows_to_services(
        [_row(GOOD_ID), _row(BAD_ID, service_type="carrier_pigeon")]
    )

    assert [service.id for service in services] == [GOOD_ID]


def test_a_malformed_verification_timestamp_only_drops_its_own_row() -> None:
    # Previously raised CatalogUnavailableError, turning one bad field into a 503 for
    # every request rather than a single missing service.
    services = PostgresServiceRegistry._rows_to_services(
        [_row(GOOD_ID), _row(BAD_ID, last_verified_at="2026-07-29")]
    )

    assert [service.id for service in services] == [GOOD_ID]


def test_a_row_missing_a_required_column_is_skipped() -> None:
    incomplete = _row(BAD_ID)
    del incomplete["launch_url"]

    services = PostgresServiceRegistry._rows_to_services([_row(GOOD_ID), incomplete])

    assert [service.id for service in services] == [GOOD_ID]


def test_healthy_rows_are_materialized_in_order() -> None:
    services = PostgresServiceRegistry._rows_to_services(
        [_row(GOOD_ID, name="Đầu"), _row(BAD_ID, name="Sau")]
    )

    assert [service.name for service in services] == ["Đầu", "Sau"]
    assert services[0].category is ServiceCategory.UTILITIES
    assert services[0].service_type is ServiceType.OA


class _capture:
    """Collect log records emitted while materializing rows."""

    def __init__(self, caplog: Any) -> None:
        self._caplog = caplog

    def __enter__(self) -> list[logging.LogRecord]:
        self._caplog.set_level(logging.ERROR, logger="domain.postgres_registry")
        self._caplog.clear()
        records: list[logging.LogRecord] = self._caplog.records
        return records

    def __exit__(self, *_exc: object) -> None:
        return None
