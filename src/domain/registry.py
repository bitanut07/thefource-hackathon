from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path
from re import split
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from domain.models import (
    RegistryService,
    ServiceCategory,
    ServiceIntent,
    ServiceType,
)
from llm.schemas import StructuredQuery

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ServiceRegistryRepository(Protocol):
    async def get_active(self, service_id: UUID) -> RegistryService | None:
        """Return an active service, or ``None`` when it is absent/inactive."""
        ...

    async def search(self, query: StructuredQuery, limit: int = 10) -> list[RegistryService]:
        """Return deterministic, active registry matches."""
        ...


class _IntentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: NonEmptyString
    example_query: NonEmptyString


class _ServiceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: NonEmptyString
    provider: NonEmptyString
    service_type: ServiceType
    category: ServiceCategory
    description: NonEmptyString
    launch_url: NonEmptyString
    owner: NonEmptyString
    active: bool = Field(strict=True)
    service_priority: int = Field(default=0, strict=True)
    region: NonEmptyString | None = None
    target_user: NonEmptyString | None = None
    organization: NonEmptyString | None = None
    last_verified_at: datetime | None = None
    aliases: tuple[NonEmptyString, ...] = ()
    intents: tuple[_IntentRecord, ...] = ()

    @model_validator(mode="after")
    def active_service_requires_auditable_verification(self) -> _ServiceRecord:
        if self.active and self.last_verified_at is None:
            raise ValueError("active service requires last_verified_at")
        if self.last_verified_at is not None and self.last_verified_at.utcoffset() is None:
            raise ValueError("last_verified_at must include a timezone")
        return self

    def to_domain(self) -> RegistryService:
        return RegistryService(
            id=self.id,
            name=self.name,
            provider=self.provider,
            service_type=self.service_type,
            category=self.category,
            description=self.description,
            launch_url=self.launch_url,
            owner=self.owner,
            active=self.active,
            service_priority=self.service_priority,
            region=self.region,
            target_user=self.target_user,
            organization=self.organization,
            last_verified_at=self.last_verified_at,
            aliases=self.aliases,
            intents=tuple(
                ServiceIntent(intent=item.intent, example_query=item.example_query)
                for item in self.intents
            ),
        )


class _RegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    notice: str | None = None
    services: tuple[_ServiceRecord, ...]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_marks).split())


_LOCATION_ALIASES = {
    "ho chi minh": "location:ho_chi_minh",
    "sai gon": "location:ho_chi_minh",
    "thanh pho ho chi minh": "location:ho_chi_minh",
    "tp hcm": "location:ho_chi_minh",
    "tphcm": "location:ho_chi_minh",
    "ha noi": "location:ha_noi",
    "thanh pho ha noi": "location:ha_noi",
    "tp ha noi": "location:ha_noi",
    "da nang": "location:da_nang",
    "hai phong": "location:hai_phong",
    "can tho": "location:can_tho",
    "toan quoc": "location:viet_nam",
    "viet nam": "location:viet_nam",
    "online": "location:online",
    "truc tuyen": "location:online",
}
_ORGANIZATION_ALIASES = {
    "cong ty vng": "organization:vng",
    "nhan vien vng": "organization:vng",
    "starter vng": "organization:vng",
    "vng": "organization:vng",
    "vng campus": "organization:vng",
    "vng corporation": "organization:vng",
}
_TARGET_USER_ALIASES = {
    "nhan vien vng": "target:vng_employee",
    "vng employee": "target:vng_employee",
}


def _filter_values(
    value: str,
    aliases: dict[str, str] | None = None,
) -> frozenset[str]:
    """Parse canonical aliases without relying on unsafe substring matching."""

    raw_parts = split(r"[;,|]", value)
    normalized_parts = {
        aliases.get(normalized, normalized) if aliases is not None else normalized
        for part in raw_parts
        if (normalized := _normalize(part))
    }
    normalized_whole = _normalize(value)
    if len(raw_parts) == 1 and normalized_whole:
        normalized_whole = (
            aliases.get(normalized_whole, normalized_whole)
            if aliases is not None
            else normalized_whole
        )
        normalized_parts.add(normalized_whole)
    return frozenset(normalized_parts)


def _matches_text_filter(
    requested: str,
    available: str | None,
    *,
    aliases: dict[str, str] | None = None,
) -> bool:
    if available is None:
        return False
    requested_values = _filter_values(requested, aliases)
    available_values = _filter_values(available, aliases)
    if not requested_values or not available_values:
        return False
    return requested_values.issubset(available_values)


def _token_coverage(needle: str, haystack: str) -> float:
    needle_tokens = set(_normalize(needle).split())
    if not needle_tokens:
        return 0.0
    haystack_tokens = set(_normalize(haystack).split())
    return len(needle_tokens & haystack_tokens) / len(needle_tokens)


class JsonServiceRegistry:
    """A validated JSON registry loaded once and searched entirely in memory."""

    path: Path

    def __init__(self, path: Path) -> None:
        self.path = path
        document = _RegistryDocument.model_validate_json(path.read_text(encoding="utf-8"))

        services_by_id: dict[UUID, RegistryService] = {}
        for record in document.services:
            service = record.to_domain()
            if service.id in services_by_id:
                raise ValueError(f"duplicate service id: {service.id}")
            services_by_id[service.id] = service

        self._services_by_id = services_by_id
        self._active_services = tuple(
            service for service in services_by_id.values() if service.active
        )

    @property
    def active_count(self) -> int:
        return len(self._active_services)

    @property
    def active_services(self) -> tuple[RegistryService, ...]:
        """Expose the immutable active set for startup/readiness validation."""

        return self._active_services

    async def get_active(self, service_id: UUID) -> RegistryService | None:
        service = self._services_by_id.get(service_id)
        if service is None or not service.active:
            return None
        return service

    async def search(self, query: StructuredQuery, limit: int = 10) -> list[RegistryService]:
        if limit <= 0 or query.out_of_scope or query.needs_clarification:
            return []

        matches = [
            service
            for service in self._active_services
            if self._matches_hard_filters(service, query)
        ]
        matches.sort(key=lambda service: self._sort_key(service, query))
        return matches[:limit]

    @staticmethod
    def _matches_hard_filters(service: RegistryService, query: StructuredQuery) -> bool:
        if query.category is not None and _normalize(query.category) != _normalize(
            service.category.value
        ):
            return False
        if query.location is not None and not _matches_text_filter(
            query.location,
            service.region,
            aliases=_LOCATION_ALIASES,
        ):
            return False
        if query.organization is not None and not _matches_text_filter(
            query.organization,
            service.organization,
            aliases=_ORGANIZATION_ALIASES,
        ):
            return False
        return query.target_user is None or _matches_text_filter(
            query.target_user,
            service.target_user,
            aliases=_TARGET_USER_ALIASES,
        )

    @staticmethod
    def _sort_key(
        service: RegistryService,
        query: StructuredQuery,
    ) -> tuple[float, float, float, float, int, str, str]:
        intent_values = " ".join(intent.intent for intent in service.intents)
        intent_exact = float(
            any(_normalize(query.intent) == _normalize(intent.intent) for intent in service.intents)
        )

        requested_service = query.service or query.intent
        service_text = " ".join(
            (
                service.name,
                service.provider,
                service.description,
                *service.aliases,
                *(intent.example_query for intent in service.intents),
            )
        )
        phrase_match = float(
            bool(_normalize(requested_service))
            and _normalize(requested_service) in _normalize(service_text)
        )
        lexical_match = max(
            _token_coverage(requested_service, service_text),
            _token_coverage(query.intent, intent_values),
        )
        organization_match = float(
            query.organization is not None
            and _matches_text_filter(
                query.organization,
                service.organization,
                aliases=_ORGANIZATION_ALIASES,
            )
        )

        return (
            -intent_exact,
            -organization_match,
            -phrase_match,
            -lexical_match,
            -service.service_priority,
            _normalize(service.name),
            str(service.id),
        )
