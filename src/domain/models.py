from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ServiceType(StrEnum):
    OA = "oa"
    MINI_APP = "mini_app"
    WEBSITE = "website"


class ServiceCategory(StrEnum):
    FOOD = "food"
    EDUCATION = "education"
    SHOPPING = "shopping"
    FINANCE = "finance"
    UTILITIES = "utilities"
    HEALTH = "health"
    GOVERNMENT = "government"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ServiceIntent:
    intent: str
    example_query: str


@dataclass(frozen=True, slots=True)
class RegistryService:
    id: UUID
    name: str
    provider: str
    service_type: ServiceType
    category: ServiceCategory
    description: str
    launch_url: str
    owner: str
    active: bool
    service_priority: int = 0
    region: str | None = None
    target_user: str | None = None
    organization: str | None = None
    last_verified_at: datetime | None = None
    aliases: tuple[str, ...] = ()
    intents: tuple[ServiceIntent, ...] = ()
