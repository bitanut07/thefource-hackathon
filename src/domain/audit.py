from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class QueryAudit:
    event_id: str
    user_hash: str | None = None
    normalized_query: str | None = None
    detected_intent: str | None = None
    candidate_ids: tuple[UUID, ...] = ()
    selected_service_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditService:
    """Minimal in-memory audit writer for local development and tests."""

    def __init__(self) -> None:
        self._entries: list[QueryAudit] = []

    @property
    def entries(self) -> tuple[QueryAudit, ...]:
        """Return an immutable snapshot in insertion order."""
        return tuple(self._entries)

    async def record(self, entry: QueryAudit) -> None:
        self._entries.append(entry)


class InMemoryAuditService(AuditService):
    """Explicit name for callers that select an in-memory audit backend."""
