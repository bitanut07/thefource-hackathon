from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import HttpUrl

from domain.models import RegistryService, ServiceType
from domain.registry import ServiceRegistryRepository
from domain.urls import is_canonical_zalo_oa_url
from llm.schemas import ServiceCandidate, StructuredQuery

SEMANTIC_WEIGHT = 0.40
INTENT_WEIGHT = 0.30
LOCATION_WEIGHT = 0.15
KEYWORD_WEIGHT = 0.10
PRIORITY_WEIGHT = 0.05
REGISTRY_CANDIDATE_LIMIT = 100
MAX_PUBLIC_CHOICES = 5
_GENERIC_SERVICE_TOKENS = frozenset(
    {
        "benh",
        "hospital",
        "medicine",
        "nha",
        "pharmacy",
        "phong",
        "service",
        "thuoc",
        "tim",
        "an",
        "uong",
        "quan",
        "do",
        "mon",
    }
)


@dataclass(frozen=True, slots=True)
class ScoreComponents:
    semantic_similarity: float
    intent_match: float
    location_match: float
    keyword_match: float
    service_priority: float


def _clamp(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))


def final_score(components: ScoreComponents) -> float:
    """Apply the agreed weights after independently clamping every component."""

    score = (
        _clamp(components.semantic_similarity) * SEMANTIC_WEIGHT
        + _clamp(components.intent_match) * INTENT_WEIGHT
        + _clamp(components.location_match) * LOCATION_WEIGHT
        + _clamp(components.keyword_match) * KEYWORD_WEIGHT
        + _clamp(components.service_priority) * PRIORITY_WEIGHT
    )
    return _clamp(score)


def _canonical_host(host: str) -> str:
    normalized = host.strip().rstrip(".")
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if not normalized:
        raise ValueError("allowed host cannot be empty")
    if any(character in normalized for character in "/?#@"):
        raise ValueError(f"allowed host must be a hostname, got {host!r}")

    try:
        return ip_address(normalized).compressed.casefold()
    except ValueError:
        try:
            return normalized.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ValueError(f"invalid allowed host: {host!r}") from exc


class LaunchUrlPolicy:
    allowed_hosts: frozenset[str]

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self.allowed_hosts = frozenset(
            _canonical_host(host) for host in allowed_hosts if host.strip()
        )

    def is_allowed(self, url: str) -> bool:
        if not url or url != url.strip() or any(ord(character) < 32 for character in url):
            return False

        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError:
            return False

        if parsed.scheme.casefold() != "https" or hostname is None:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False

        try:
            canonical_hostname = _canonical_host(hostname)
        except ValueError:
            return False
        return canonical_hostname in self.allowed_hosts

    def is_allowed_for_service(self, service_type: ServiceType, url: str) -> bool:
        """Apply both the host allowlist and channel-specific URL contract."""

        if not self.is_allowed(url):
            return False
        if service_type is ServiceType.OA:
            return is_canonical_zalo_oa_url(url)
        return True


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_marks).split())


def _coverage(needle: str, haystack: str) -> float:
    needle_tokens = set(_normalize(needle).split())
    if not needle_tokens:
        return 0.0
    haystack_tokens = set(_normalize(haystack).split())
    return len(needle_tokens & haystack_tokens) / len(needle_tokens)


def _service_text(service: RegistryService) -> str:
    return " ".join(
        (
            service.name,
            service.provider,
            service.category.value,
            service.description,
            service.region or "",
            service.target_user or "",
            service.organization or "",
            *service.aliases,
            *(intent.intent for intent in service.intents),
            *(intent.example_query for intent in service.intents),
        )
    )


def _semantic_similarity(query: StructuredQuery, service: RegistryService) -> float:
    query_text = " ".join(
        value
        for value in (
            query.intent,
            query.category,
            query.service,
            query.location,
            query.target_user,
            query.organization,
        )
        if value is not None
    )
    return _coverage(query_text, _service_text(service))


def _intent_match(query: StructuredQuery, service: RegistryService) -> float:
    normalized_intent = _normalize(query.intent)
    if any(normalized_intent == _normalize(intent.intent) for intent in service.intents):
        return 1.0
    return max(
        (_coverage(query.intent, intent.intent) for intent in service.intents),
        default=0.0,
    )


def _location_match(query: StructuredQuery, service: RegistryService) -> float:
    if query.location is None or service.region is None:
        return 0.0
    requested = _normalize_location(query.location)
    available = _normalize_location(service.region)
    if requested == available or requested in available or available in requested:
        return 1.0
    return _coverage(query.location, service.region)


def _normalize_location(value: str) -> str:
    normalized = _normalize(value)
    aliases = {
        "hcm": "thanh pho ho chi minh",
        "tphcm": "thanh pho ho chi minh",
        "tp hcm": "thanh pho ho chi minh",
        "ho chi minh": "thanh pho ho chi minh",
    }
    return aliases.get(normalized, normalized)


def _keyword_match(query: StructuredQuery, service: RegistryService) -> float:
    requested = query.service or query.intent
    names_and_aliases = " ".join((service.name, service.description, *service.aliases))
    normalized_requested = _normalize(requested)
    normalized_service = _normalize(names_and_aliases)
    if normalized_requested and normalized_requested in normalized_service:
        return 1.0
    return _coverage(requested, names_and_aliases)


def _is_specific_service_match(query: StructuredQuery, service: RegistryService) -> bool:
    """Detect an explicit provider/name request without treating generic needs as one."""

    if query.service is None:
        return False
    entity_tokens = {
        token for token in _normalize(query.service).split() if token not in _GENERIC_SERVICE_TOKENS
    }
    if not entity_tokens:
        return False
    labels = " ".join((service.name, *service.aliases))
    label_tokens = set(_normalize(labels).split())
    if not entity_tokens.issubset(label_tokens):
        return False
    return len(entity_tokens) >= 2 or any(len(token) >= 3 for token in entity_tokens)


def _has_service_constraint(query: StructuredQuery) -> bool:
    if query.service is None:
        return False
    return any(
        token not in _GENERIC_SERVICE_TOKENS
        for token in _normalize(query.service).split()
    )


def _matches_service_constraint(query: StructuredQuery, service: RegistryService) -> bool:
    """Do not treat a category match as a match for a named dish/service."""

    if not _has_service_constraint(query) or query.service is None:
        return True
    requested = _sensitive_tokens(query.service)
    available = _sensitive_tokens(_service_text(service))
    return bool(requested) and requested.issubset(available)


def _sensitive_tokens(value: str) -> set[str]:
    """Keep Vietnamese tone marks for dish terms (``lẩu`` must not match ``lâu``)."""

    return {
        token
        for token in "".join(char if char.isalnum() else " " for char in value.casefold()).split()
    }


def _reason(query: StructuredQuery, service: RegistryService, components: ScoreComponents) -> str:
    reasons: list[str] = []
    if components.intent_match == 1.0:
        reasons.append("khớp nhu cầu")
    if query.location is not None and components.location_match > 0.0:
        reasons.append(f"phù hợp khu vực {service.region}")
    if (
        query.organization is not None
        and service.organization is not None
        and _normalize(query.organization) == _normalize(service.organization)
    ):
        reasons.append(f"phù hợp ngữ cảnh {service.organization}")
    if query.service is not None and components.keyword_match >= 0.75:
        reasons.append(f"khớp dịch vụ {query.service}")
    return ", ".join(reasons) if reasons else "phù hợp nhất trong danh mục dịch vụ"


class SearchService:
    registry: ServiceRegistryRepository
    url_policy: LaunchUrlPolicy

    def __init__(
        self,
        registry: ServiceRegistryRepository,
        url_policy: LaunchUrlPolicy,
    ) -> None:
        self.registry = registry
        self.url_policy = url_policy

    async def search(
        self,
        query: StructuredQuery,
        limit: int = MAX_PUBLIC_CHOICES,
    ) -> list[ServiceCandidate]:
        if limit <= 0 or query.out_of_scope or query.needs_clarification:
            return []

        services = await self.registry.search(
            query,
            limit=max(REGISTRY_CANDIDATE_LIMIT, limit),
        )
        eligible_services = [
            service
            for service in services
            if service.active
            and self.url_policy.is_allowed_for_service(
                service.service_type,
                service.launch_url,
            )
        ]
        if query.location is not None:
            # A ranked PostgreSQL result set can omit a local record before this
            # layer gets to apply its contract. Inspect the publishable catalog
            # too, then keep the local subset whenever one exists.
            catalog_services = await self.registry.list_active()
            local_services = [
                service
                for service in catalog_services
                if service.active
                and (query.category is None or service.category.value == query.category)
                and self.url_policy.is_allowed_for_service(
                    service.service_type,
                    service.launch_url,
                )
                and _location_match(query, service) >= 0.5
            ]
            # An explicit location is a hard constraint when the registry has
            # local records; never silently mix other cities into the result.
            if local_services:
                eligible_services = local_services
        maximum_priority = max(
            (max(service.service_priority, 0) for service in eligible_services),
            default=0,
        )

        ranked: list[tuple[ServiceCandidate, ScoreComponents, RegistryService]] = []
        for service in eligible_services:
            priority_score = (
                max(service.service_priority, 0) / maximum_priority if maximum_priority > 0 else 0.0
            )
            components = ScoreComponents(
                semantic_similarity=_semantic_similarity(query, service),
                intent_match=_intent_match(query, service),
                location_match=_location_match(query, service),
                keyword_match=_keyword_match(query, service),
                service_priority=priority_score,
            )
            candidate = ServiceCandidate(
                service_id=service.id,
                name=service.name,
                service_type=service.service_type.value,
                launch_url=HttpUrl(service.launch_url),
                region=service.region,
                organization=service.organization,
                reason=_reason(query, service, components),
                score=final_score(components),
            )
            ranked.append((candidate, components, service))

        ranked.sort(
            key=lambda item: (
                -item[0].score,
                -item[1].intent_match,
                -item[1].keyword_match,
                -item[2].service_priority,
                _normalize(item[2].name),
                str(item[2].id),
            )
        )
        explicit_matches = [
            candidate
            for candidate, _, service in ranked
            if _is_specific_service_match(query, service)
        ]
        if explicit_matches:
            return explicit_matches[:limit]

        # Do not fill a response merely to reach its maximum size. Candidates
        # must remain reasonably close to the strongest result.
        best_score = ranked[0][0].score if ranked else 0.0
        relevance_threshold = max(0.10, best_score * 0.70)
        relevant = [
            candidate
            for candidate, components, _ in ranked
            if candidate.score >= relevance_threshold
            and _matches_service_constraint(query, _)
            and (
                components.intent_match > 0.0
                or components.keyword_match >= 0.25
                or components.semantic_similarity >= 0.25
            )
        ]
        return relevant[:limit]
