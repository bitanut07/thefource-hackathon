from __future__ import annotations

from datetime import datetime
from pathlib import Path
from re import split
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from domain.entity_normalization import normalize_entity, normalize_text
from domain.models import (
    RegistryService,
    ServiceCategory,
    ServiceIntent,
    ServiceType,
)
from domain.urls import is_canonical_zalo_oa_url
from llm.schemas import StructuredQuery

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ServiceRegistryRepository(Protocol):
    async def list_active(self) -> tuple[RegistryService, ...]:
        """Return every publishable service for inspection and readiness checks."""
        ...

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
    chatbot_image_url: HttpUrl | None = None
    last_verified_at: datetime | None = None
    aliases: tuple[NonEmptyString, ...] = ()
    intents: tuple[_IntentRecord, ...] = ()

    @model_validator(mode="after")
    def active_service_requires_auditable_verification(self) -> _ServiceRecord:
        if self.active and self.last_verified_at is None:
            raise ValueError("active service requires last_verified_at")
        if self.last_verified_at is not None and self.last_verified_at.utcoffset() is None:
            raise ValueError("last_verified_at must include a timezone")
        if self.service_type is ServiceType.OA and not is_canonical_zalo_oa_url(self.launch_url):
            raise ValueError("OA launch_url must use canonical https://zalo.me/<numeric-oa-id>")
        if self.chatbot_image_url is not None and self.chatbot_image_url.scheme != "https":
            raise ValueError("chatbot_image_url must use HTTPS")
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
            chatbot_image_url=(str(self.chatbot_image_url) if self.chatbot_image_url else None),
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
    return normalize_text(value)


def _filter_values(
    value: str,
    namespace: str | None = None,
) -> frozenset[str]:
    """Parse canonical aliases without relying on unsafe substring matching."""

    raw_parts = split(r"[;,|]", value)
    normalized_parts = {
        normalize_entity(part, namespace) if namespace is not None else normalized
        for part in raw_parts
        if (normalized := _normalize(part))
    }
    normalized_whole = _normalize(value)
    if len(raw_parts) == 1 and normalized_whole:
        if namespace is not None:
            normalized_whole = normalize_entity(value, namespace)
        normalized_parts.add(normalized_whole)
    return frozenset(normalized_parts)


def _matches_text_filter(
    requested: str,
    available: str | None,
    *,
    namespace: str | None = None,
) -> bool:
    if available is None:
        return False
    requested_values = _filter_values(requested, namespace)
    available_values = _filter_values(available, namespace)
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

    async def list_active(self) -> tuple[RegistryService, ...]:
        return self._active_services

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
            namespace="location",
        ):
            return False
        if query.organization is not None and not _matches_text_filter(
            query.organization,
            service.organization,
            namespace="organization",
        ):
            return False
        return query.target_user is None or _matches_text_filter(
            query.target_user,
            service.target_user,
            namespace="target_user",
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
                namespace="organization",
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
