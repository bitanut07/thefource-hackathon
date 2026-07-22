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
    async def record(self, entry: QueryAudit) -> None:
        # TODO: Ghi audit đã giảm thiểu dữ liệu vào nơi lưu trữ được cấu hình.
        raise NotImplementedError("Chưa triển khai ghi audit truy vấn")
