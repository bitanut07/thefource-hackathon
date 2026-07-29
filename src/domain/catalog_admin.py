"""Reviewer-facing catalog domain: statuses, records and publish guardrails.

The runtime registry (``domain.registry.ServiceRegistryRepository``) is read-only
and only ever materializes publishable rows.  Review tooling needs the opposite:
every row regardless of status, plus the rules that decide whether a row is
allowed to become publishable at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from domain.models import ServiceCategory, ServiceIntent, ServiceType
from domain.search import LaunchUrlPolicy

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Navigator only publishes Zalo-native destinations; see migration 002.
PUBLISHABLE_SERVICE_TYPES = frozenset({ServiceType.OA, ServiceType.MINI_APP})


class ReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


# Mirrors ``domain.postgres_registry._PUBLISHED_STATUSES``; both must agree or a
# reviewer could approve a row the runtime refuses to serve.
PUBLISHABLE_REVIEW_STATUSES = frozenset({ReviewStatus.APPROVED, ReviewStatus.PUBLISHED})


class ReviewAction(StrEnum):
    CREATE = "create"
    IMPORT = "import"
    UPDATE = "update"
    APPROVE = "approve"
    REJECT = "reject"
    DEACTIVATE = "deactivate"
    DELETE = "delete"
    RESTORE = "restore"


class PublishGuardError(RuntimeError):
    """A write would leave a served row in a state the runtime cannot serve."""

    def __init__(self, blockers: tuple[str, ...]) -> None:
        super().__init__("; ".join(blockers))
        self.blockers = blockers


@dataclass(frozen=True, slots=True)
class ServiceEvidence:
    """A recorded source backing a service's identity, shown to reviewers.

    ``supports`` is the claim explaining how the source ties the provider to this
    launch URL; it is what an approval decision actually rests on.
    """

    source_url: str
    publisher: str | None = None
    checked_at: datetime | None = None
    verification_status: str = "candidate"
    supports: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewEvent:
    """One audited change to a catalog row."""

    action: str
    actor: str
    created_at: datetime
    note: str | None = None
    changed_fields: tuple[str, ...] = ()
    previous_review_status: str | None = None
    new_review_status: str | None = None


@dataclass(frozen=True, slots=True)
class AdminServiceRecord:
    """A catalog row as reviewers see it, including non-publishable rows.

    ``category`` and ``review_status`` stay raw strings on purpose: research rows
    may carry values outside the runtime enums, and a reviewer has to be able to
    read such a row in order to fix it.  Writes are validated against the enums.
    """

    id: UUID
    name: str
    provider: str
    service_type: ServiceType
    category: str
    description: str
    launch_url: str
    owner: str
    active: bool
    review_status: str
    service_priority: int
    source_type: str
    has_embedding: bool
    region: str | None = None
    target_user: str | None = None
    organization: str | None = None
    last_verified_at: datetime | None = None
    updated_at: datetime | None = None
    # Set when the row was removed. The schema guarantees a removed row is never
    # served, so runtime queries need no extra filter.
    deleted_at: datetime | None = None
    aliases: tuple[str, ...] = ()
    intents: tuple[ServiceIntent, ...] = ()
    evidence: tuple[ServiceEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogStats:
    """Aggregate counts backing the review dashboard header."""

    # Counts describe live rows; removed rows are reported separately so a growing
    # deleted pile never inflates the catalog size.
    total: int
    publishable: int
    missing_embedding: int
    deleted: int
    by_review_status: tuple[tuple[str, int], ...]
    by_category: tuple[tuple[str, int], ...]
    by_source_type: tuple[tuple[str, int], ...]


def publish_blockers(
    record: AdminServiceRecord,
    url_policy: LaunchUrlPolicy,
) -> tuple[str, ...]:
    """Return every reason ``record`` must not be served to end users.

    Approval calls this to refuse bad rows, and listings surface it so a reviewer
    sees the problem before clicking.  Each check guards a concrete failure:

    * a non-Zalo channel violates the constraint added by migration 002;
    * an off-enum category makes ``PostgresServiceRegistry`` raise while building
      a ``RegistryService``, which is an uncaught ``ValueError`` on every
      ``/navigate`` request rather than a handled catalog error;
    * a launch URL outside the allowlist, or a non-canonical OA deeplink, is
      exactly what the response builder is designed never to emit.
    """

    blockers: list[str] = []
    if record.deleted_at is not None:
        blockers.append("Dịch vụ đã bị xóa; phục hồi trước khi duyệt lại.")
    if record.service_type not in PUBLISHABLE_SERVICE_TYPES:
        blockers.append(
            f"service_type {record.service_type.value} không được publish; "
            "chỉ nhận oa hoặc mini_app."
        )
    if record.category not in frozenset(item.value for item in ServiceCategory):
        blockers.append(
            f"category {record.category!r} nằm ngoài danh mục runtime; "
            "publish sẽ làm /navigate lỗi khi dựng service."
        )
    if not url_policy.is_allowed(record.launch_url):
        blockers.append("launch_url không thuộc allowlist host hoặc không dùng HTTPS.")
    elif not url_policy.is_allowed_for_service(record.service_type, record.launch_url):
        blockers.append("launch_url OA phải là deeplink số chuẩn dạng https://zalo.me/<oa_id>.")
    return tuple(blockers)


class _IntentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: NonEmptyString
    example_query: NonEmptyString


# Editing any of these invalidates the row's stored embedding and search_text.
SEARCH_TEXT_FIELDS = frozenset(
    {
        "name",
        "provider",
        "category",
        "description",
        "region",
        "target_user",
        "organization",
        "aliases",
        "intents",
    }
)


class ServicePatch(BaseModel):
    """Fields a reviewer may change.  Unset fields are left untouched.

    ``category`` and ``service_type`` accept only runtime enum values so an edit
    can never introduce a row the navigator cannot materialize.
    """

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString | None = None
    provider: NonEmptyString | None = None
    service_type: ServiceType | None = None
    category: ServiceCategory | None = None
    description: NonEmptyString | None = None
    launch_url: NonEmptyString | None = None
    service_priority: int | None = Field(default=None, ge=0, le=100)
    region: str | None = None
    target_user: str | None = None
    organization: str | None = None
    aliases: tuple[NonEmptyString, ...] | None = None
    intents: tuple[_IntentInput, ...] | None = None

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> ServicePatch:
        if not self.model_fields_set:
            raise ValueError("patch phải chứa ít nhất một trường cần đổi")
        return self

    def changed_fields(self) -> tuple[str, ...]:
        return tuple(sorted(self.model_fields_set))

    def invalidates_search_text(self) -> bool:
        return bool(self.model_fields_set & SEARCH_TEXT_FIELDS)


class ServiceDraft(BaseModel):
    """A brand-new catalog row.  Created unpublished so approval stays explicit."""

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    provider: NonEmptyString
    service_type: ServiceType
    category: ServiceCategory
    description: NonEmptyString
    launch_url: NonEmptyString
    service_priority: int = Field(default=0, ge=0, le=100)
    region: str | None = None
    target_user: str | None = None
    organization: str | None = None
    aliases: tuple[NonEmptyString, ...] = ()
    intents: tuple[_IntentInput, ...] = ()


def build_search_text(
    *,
    name: str,
    provider: str,
    category: str,
    description: str,
    region: str | None,
    target_user: str | None,
    organization: str | None,
    aliases: tuple[str, ...],
    intents: tuple[ServiceIntent, ...],
) -> str:
    """Rebuild the lexical search column.

    Field order and content mirror ``scripts/seed_postgres.joined_text`` so a row
    edited through the API ranks the same as one imported by the seeder.
    """

    values = [
        name,
        provider,
        category,
        description,
        region or "",
        target_user or "",
        organization or "",
        *aliases,
        *(intent.intent for intent in intents),
        *(intent.example_query for intent in intents),
    ]
    return " ".join(value.strip() for value in values if value and value.strip())


class AdminCatalogRepository(Protocol):
    """Read/write access to every catalog row, publishable or not."""

    async def list_services(
        self,
        *,
        review_status: str | None = None,
        service_type: ServiceType | None = None,
        active: bool | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        deleted_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[tuple[AdminServiceRecord, ...], int]:
        """Return a page of records plus the total matching count."""
        ...

    async def get_service(self, service_id: UUID) -> AdminServiceRecord | None:
        """Return one record with its evidence, or ``None`` when absent."""
        ...

    async def find_by_launch_url(self, launch_url: str) -> AdminServiceRecord | None:
        """Return any existing row with this launch URL, removed rows included."""
        ...

    async def create_service(
        self,
        draft: ServiceDraft,
        *,
        actor: str,
        note: str | None = None,
        action: ReviewAction = ReviewAction.CREATE,
    ) -> AdminServiceRecord:
        """Insert an unpublished row and audit the creation."""
        ...

    async def update_service(
        self,
        service_id: UUID,
        patch: ServicePatch,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Apply a partial edit and audit the changed field names."""
        ...

    async def approve_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        verified_at: datetime,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Make a row publishable and stamp the verification time."""
        ...

    async def reject_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Mark a row rejected and withdraw it from serving."""
        ...

    async def deactivate_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Withdraw a row from serving while keeping its review history."""
        ...

    async def delete_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Mark a row removed, keeping its evidence and audit trail readable."""
        ...

    async def restore_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Clear a removal mark, leaving the row unpublished."""
        ...

    async def stats(self) -> CatalogStats:
        """Return aggregate catalog counts."""
        ...

    async def review_events(self, service_id: UUID, *, limit: int = 50) -> tuple[ReviewEvent, ...]:
        """Return the audit trail for one row, newest first."""
        ...
