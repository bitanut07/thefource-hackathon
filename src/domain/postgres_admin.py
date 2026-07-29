"""PostgreSQL read/write access for the catalog review console.

Kept separate from :mod:`domain.postgres_registry` on purpose.  That module is the
runtime read path and must only ever materialize publishable rows; this one sees
every row and is the only place allowed to change what becomes publishable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from domain.catalog_admin import (
    PUBLISHABLE_REVIEW_STATUSES,
    AdminServiceRecord,
    CatalogStats,
    PublishGuardError,
    ReviewAction,
    ReviewEvent,
    ReviewStatus,
    ServiceDraft,
    ServiceEvidence,
    ServicePatch,
    build_search_text,
    publish_blockers,
)
from domain.models import ServiceIntent, ServiceType
from domain.postgres_registry import CatalogUnavailableError
from domain.search import LaunchUrlPolicy

CONSOLE_OWNER = "review-console"
CONSOLE_SOURCE_TYPE = "console"

_ADMIN_DETAILS = """
    s.id, s.name, s.provider, s.service_type, s.category, s.description,
    s.launch_url, s.owner, s.active, s.review_status, s.service_priority,
    s.region, s.target_user, s.organization, s.last_verified_at,
    s.source_type, s.updated_at, s.deleted_at,
    (s.embedding IS NOT NULL) AS has_embedding,
    COALESCE((
        SELECT array_agg(a.alias ORDER BY a.alias)
        FROM service_aliases AS a
        WHERE a.service_id = s.id
    ), ARRAY[]::text[]) AS aliases,
    COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'intent', i.intent,
            'example_query', i.example_query
        ) ORDER BY i.intent, i.example_query)
        FROM service_intents AS i
        WHERE i.service_id = s.id
    ), '[]'::jsonb) AS intents,
    COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'source_url', e.source_url,
            'publisher', e.publisher,
            'checked_at', e.checked_at,
            'verification_status', e.verification_status,
            'supports', e.supports
        ) ORDER BY e.source_url)
        FROM service_evidence AS e
        WHERE e.service_id = s.id
    ), '[]'::jsonb) AS evidence
"""


def _like_pattern(query: str) -> str:
    """Build a case-insensitive contains pattern with LIKE metacharacters escaped."""

    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class PostgresAdminCatalog:
    """Every catalog row plus the audited transitions between review states.

    ``url_policy`` is a constructor dependency because "a served row always passes
    the launch-URL contract" is an invariant of the catalog itself, not of the HTTP
    layer: enforcing it here means no caller can bypass it.
    """

    def __init__(self, database_url: str, *, url_policy: LaunchUrlPolicy) -> None:
        if not database_url.strip():
            raise ValueError("database_url cannot be empty for the review console")
        self._database_url = database_url
        self._url_policy = url_policy

    # ------------------------------------------------------------------ reads

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
        return await asyncio.to_thread(
            self._list_services_sync,
            review_status,
            service_type,
            active,
            query,
            include_deleted,
            deleted_only,
            offset,
            limit,
        )

    async def get_service(self, service_id: UUID) -> AdminServiceRecord | None:
        return await asyncio.to_thread(self._get_service_sync, service_id)

    async def stats(self) -> CatalogStats:
        return await asyncio.to_thread(self._stats_sync)

    async def review_events(self, service_id: UUID, *, limit: int = 50) -> tuple[ReviewEvent, ...]:
        return await asyncio.to_thread(self._review_events_sync, service_id, limit)

    # ----------------------------------------------------------------- writes

    async def create_service(
        self,
        draft: ServiceDraft,
        *,
        actor: str,
        note: str | None = None,
        action: ReviewAction = ReviewAction.CREATE,
    ) -> AdminServiceRecord:
        return await asyncio.to_thread(self._create_service_sync, draft, actor, note, action)

    async def update_service(
        self,
        service_id: UUID,
        patch: ServicePatch,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        return await asyncio.to_thread(self._update_service_sync, service_id, patch, actor, note)

    async def approve_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        verified_at: datetime,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        return await asyncio.to_thread(
            self._approve_service_sync, service_id, actor, verified_at, note
        )

    async def reject_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        return await asyncio.to_thread(
            self._set_withdrawn_sync,
            service_id,
            ReviewStatus.REJECTED.value,
            ReviewAction.REJECT,
            actor,
            note,
        )

    async def deactivate_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        # Keeps review_status so an operational pause stays distinguishable from a
        # review decision; the schema only requires a publishable status while active.
        return await asyncio.to_thread(
            self._set_withdrawn_sync,
            service_id,
            None,
            ReviewAction.DEACTIVATE,
            actor,
            note,
        )

    async def delete_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Mark a row removed, withdrawing it from serving in the same statement."""

        return await asyncio.to_thread(self._delete_service_sync, service_id, actor, note)

    async def restore_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        """Clear the removal mark, leaving the row unpublished for re-review."""

        return await asyncio.to_thread(self._restore_service_sync, service_id, actor, note)

    async def find_by_launch_url(self, launch_url: str) -> AdminServiceRecord | None:
        """Look up an existing row by launch URL, including removed ones.

        Import uses this to refuse duplicates: two rows sharing a deeplink would make
        the assistant offer the same destination twice.
        """

        return await asyncio.to_thread(self._find_by_launch_url_sync, launch_url)

    # ------------------------------------------------------------- internals

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        try:
            return psycopg.connect(
                self._database_url,
                connect_timeout=3,
                row_factory=dict_row,
            )
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể kết nối Service Catalog PostgreSQL.") from exc

    def _list_services_sync(
        self,
        review_status: str | None,
        service_type: ServiceType | None,
        active: bool | None,
        query: str | None,
        include_deleted: bool,
        deleted_only: bool,
        offset: int,
        limit: int,
    ) -> tuple[tuple[AdminServiceRecord, ...], int]:
        # count(*) OVER () is evaluated before LIMIT, so one round trip yields both
        # the page and the unpaged total.
        statement = f"""
            SELECT {_ADMIN_DETAILS}, count(*) OVER () AS total_count
            FROM services AS s
            WHERE (%(review_status)s::text IS NULL OR s.review_status = %(review_status)s::text)
              AND (%(service_type)s::text IS NULL OR s.service_type = %(service_type)s::text)
              AND (%(active)s::boolean IS NULL OR s.active = %(active)s::boolean)
              -- Removed rows stay hidden unless asked for, so a reviewer never acts
              -- on a record that is no longer part of the catalog by accident.
              AND CASE
                    WHEN %(deleted_only)s::boolean THEN s.deleted_at IS NOT NULL
                    WHEN %(include_deleted)s::boolean THEN TRUE
                    ELSE s.deleted_at IS NULL
                  END
              AND (
                    %(pattern)s::text IS NULL
                    OR s.name ILIKE %(pattern)s::text
                    OR s.search_text ILIKE %(pattern)s::text
              )
            ORDER BY s.active ASC, s.name ASC, s.id ASC
            OFFSET %(offset)s LIMIT %(limit)s
        """
        parameters = {
            "review_status": review_status,
            "service_type": service_type.value if service_type is not None else None,
            "active": active,
            "pattern": _like_pattern(query) if query and query.strip() else None,
            "include_deleted": include_deleted,
            "deleted_only": deleted_only,
            "offset": offset,
            "limit": limit,
        }
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                rows = cursor.fetchall()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể đọc Service Catalog PostgreSQL.") from exc
        total = int(rows[0]["total_count"]) if rows else 0
        return tuple(self._row_to_record(row) for row in rows), total

    def _get_service_sync(self, service_id: UUID) -> AdminServiceRecord | None:
        statement = f"SELECT {_ADMIN_DETAILS} FROM services AS s WHERE s.id = %s"
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, (service_id,))
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể đọc Service Catalog PostgreSQL.") from exc
        return self._row_to_record(row) if row is not None else None

    def _stats_sync(self) -> CatalogStats:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*) FILTER (WHERE deleted_at IS NULL) AS total,
                           count(*) FILTER (
                               WHERE deleted_at IS NULL
                                 AND active
                                 AND review_status = ANY(%(publishable)s)
                           ) AS publishable,
                           count(*) FILTER (
                               WHERE deleted_at IS NULL AND embedding IS NULL
                           ) AS missing_embedding,
                           count(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted
                    FROM services
                    """,
                    {"publishable": sorted(item.value for item in PUBLISHABLE_REVIEW_STATUSES)},
                )
                totals = cursor.fetchone()
                if totals is None:
                    raise CatalogUnavailableError("Service Catalog không trả được số liệu tổng.")
                grouped: dict[str, tuple[tuple[str, int], ...]] = {}
                for column in ("review_status", "category", "source_type"):
                    cursor.execute(
                        f"SELECT {column} AS label, count(*) AS count "
                        f"FROM services WHERE deleted_at IS NULL "
                        f"GROUP BY {column} ORDER BY {column}"
                    )
                    grouped[column] = tuple(
                        (str(row["label"]), int(row["count"])) for row in cursor.fetchall()
                    )
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể đọc số liệu Service Catalog.") from exc
        return CatalogStats(
            total=int(totals["total"]),
            publishable=int(totals["publishable"]),
            missing_embedding=int(totals["missing_embedding"]),
            deleted=int(totals["deleted"]),
            by_review_status=grouped["review_status"],
            by_category=grouped["category"],
            by_source_type=grouped["source_type"],
        )

    def _review_events_sync(self, service_id: UUID, limit: int) -> tuple[ReviewEvent, ...]:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT action, actor, note, changed_fields,
                           previous_review_status, new_review_status, created_at
                    FROM service_review_events
                    WHERE service_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (service_id, limit),
                )
                rows = cursor.fetchall()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể đọc lịch sử review.") from exc
        return tuple(
            ReviewEvent(
                action=str(row["action"]),
                actor=str(row["actor"]),
                created_at=row["created_at"],
                note=_optional_text(row["note"]),
                changed_fields=tuple(str(field) for field in row["changed_fields"] or ()),
                previous_review_status=_optional_text(row["previous_review_status"]),
                new_review_status=_optional_text(row["new_review_status"]),
            )
            for row in rows
        )

    def _create_service_sync(
        self,
        draft: ServiceDraft,
        actor: str,
        note: str | None,
        action: ReviewAction = ReviewAction.CREATE,
    ) -> AdminServiceRecord:
        service_id = uuid4()
        intents = tuple(
            ServiceIntent(intent=item.intent, example_query=item.example_query)
            for item in draft.intents
        )
        search_text = build_search_text(
            name=draft.name,
            provider=draft.provider,
            category=draft.category.value,
            description=draft.description,
            region=draft.region,
            target_user=draft.target_user,
            organization=draft.organization,
            aliases=tuple(draft.aliases),
            intents=intents,
        )
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    # Always unpublished: creating a row and deciding to serve it are
                    # separate, separately audited acts.
                    cursor.execute(
                        """
                        INSERT INTO services (
                            id, name, provider, service_type, category, description,
                            launch_url, owner, active, review_status, service_priority,
                            region, target_user, organization, last_verified_at,
                            search_text, source_type
                        ) VALUES (
                            %(id)s, %(name)s, %(provider)s, %(service_type)s, %(category)s,
                            %(description)s, %(launch_url)s, %(owner)s, FALSE,
                            %(review_status)s, %(service_priority)s, %(region)s,
                            %(target_user)s, %(organization)s, NULL,
                            %(search_text)s, %(source_type)s
                        )
                        """,
                        {
                            "id": service_id,
                            "name": draft.name,
                            "provider": draft.provider,
                            "service_type": draft.service_type.value,
                            "category": draft.category.value,
                            "description": draft.description,
                            "launch_url": draft.launch_url,
                            "owner": CONSOLE_OWNER,
                            "review_status": ReviewStatus.CANDIDATE.value,
                            "service_priority": draft.service_priority,
                            "region": draft.region,
                            "target_user": draft.target_user,
                            "organization": draft.organization,
                            "search_text": search_text,
                            "source_type": CONSOLE_SOURCE_TYPE,
                        },
                    )
                    self._replace_children(cursor, service_id, tuple(draft.aliases), intents)
                    self._record_event(
                        cursor,
                        service_id=service_id,
                        action=action,
                        actor=actor,
                        note=note,
                        changed_fields=(),
                        previous_review_status=None,
                        new_review_status=ReviewStatus.CANDIDATE.value,
                    )
                connection.commit()
        except psycopg.Error as exc:
            raise CatalogUnavailableError(
                "Không thể tạo dịch vụ mới trong Service Catalog."
            ) from exc
        created = self._get_service_sync(service_id)
        if created is None:
            raise CatalogUnavailableError("Dịch vụ vừa tạo không đọc lại được.")
        return created

    def _update_service_sync(
        self,
        service_id: UUID,
        patch: ServicePatch,
        actor: str,
        note: str | None,
    ) -> AdminServiceRecord | None:
        changes = patch.model_dump(exclude_unset=True)
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    current = self._locked_row(cursor, service_id)
                    if current is None:
                        return None

                    service_type = (
                        patch.service_type
                        if patch.service_type is not None
                        else current.service_type
                    )
                    category = (
                        patch.category.value if patch.category is not None else current.category
                    )
                    aliases = tuple(patch.aliases) if patch.aliases is not None else current.aliases
                    intents = (
                        tuple(
                            ServiceIntent(intent=item.intent, example_query=item.example_query)
                            for item in patch.intents
                        )
                        if patch.intents is not None
                        else current.intents
                    )
                    merged = AdminServiceRecord(
                        id=current.id,
                        name=changes.get("name", current.name),
                        provider=changes.get("provider", current.provider),
                        service_type=service_type,
                        category=category,
                        description=changes.get("description", current.description),
                        launch_url=changes.get("launch_url", current.launch_url),
                        owner=current.owner,
                        active=current.active,
                        review_status=current.review_status,
                        service_priority=changes.get("service_priority", current.service_priority),
                        source_type=current.source_type,
                        has_embedding=current.has_embedding,
                        region=changes.get("region", current.region),
                        target_user=changes.get("target_user", current.target_user),
                        organization=changes.get("organization", current.organization),
                        last_verified_at=current.last_verified_at,
                        aliases=aliases,
                        intents=intents,
                    )
                    # A row that is already being served must not be edited into a
                    # state the runtime cannot serve.
                    if merged.active:
                        blockers = publish_blockers(merged, self._url_policy)
                        if blockers:
                            raise PublishGuardError(blockers)

                    search_text = build_search_text(
                        name=merged.name,
                        provider=merged.provider,
                        category=merged.category,
                        description=merged.description,
                        region=merged.region,
                        target_user=merged.target_user,
                        organization=merged.organization,
                        aliases=merged.aliases,
                        intents=merged.intents,
                    )
                    # Editing the searchable text leaves any stored vector describing
                    # the old wording. Dropping it makes the semantic lane contribute
                    # zero for this row until `make catalog-embed` regenerates it,
                    # which is preferable to ranking on stale meaning.
                    drop_embedding = patch.invalidates_search_text()
                    cursor.execute(
                        """
                        UPDATE services SET
                            name = %(name)s,
                            provider = %(provider)s,
                            service_type = %(service_type)s,
                            category = %(category)s,
                            description = %(description)s,
                            launch_url = %(launch_url)s,
                            service_priority = %(service_priority)s,
                            region = %(region)s,
                            target_user = %(target_user)s,
                            organization = %(organization)s,
                            search_text = %(search_text)s,
                            embedding = CASE
                                WHEN %(drop_embedding)s THEN NULL ELSE embedding
                            END,
                            updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {
                            "id": service_id,
                            "name": merged.name,
                            "provider": merged.provider,
                            "service_type": merged.service_type.value,
                            "category": merged.category,
                            "description": merged.description,
                            "launch_url": merged.launch_url,
                            "service_priority": merged.service_priority,
                            "region": merged.region,
                            "target_user": merged.target_user,
                            "organization": merged.organization,
                            "search_text": search_text,
                            "drop_embedding": drop_embedding,
                        },
                    )
                    if patch.aliases is not None or patch.intents is not None:
                        self._replace_children(cursor, service_id, aliases, intents)
                    self._record_event(
                        cursor,
                        service_id=service_id,
                        action=ReviewAction.UPDATE,
                        actor=actor,
                        note=note,
                        changed_fields=patch.changed_fields(),
                        previous_review_status=current.review_status,
                        new_review_status=current.review_status,
                    )
                connection.commit()
        except psycopg.Error as exc:
            raise CatalogUnavailableError(
                "Không thể cập nhật dịch vụ trong Service Catalog."
            ) from exc
        return self._get_service_sync(service_id)

    def _approve_service_sync(
        self,
        service_id: UUID,
        actor: str,
        verified_at: datetime,
        note: str | None,
    ) -> AdminServiceRecord | None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    current = self._locked_row(cursor, service_id)
                    if current is None:
                        return None
                    blockers = publish_blockers(current, self._url_policy)
                    if blockers:
                        raise PublishGuardError(blockers)
                    cursor.execute(
                        """
                        UPDATE services
                        SET active = TRUE,
                            review_status = %(review_status)s,
                            last_verified_at = %(verified_at)s,
                            updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {
                            "id": service_id,
                            "review_status": ReviewStatus.APPROVED.value,
                            "verified_at": verified_at,
                        },
                    )
                    self._record_event(
                        cursor,
                        service_id=service_id,
                        action=ReviewAction.APPROVE,
                        actor=actor,
                        note=note,
                        changed_fields=("active", "last_verified_at", "review_status"),
                        previous_review_status=current.review_status,
                        new_review_status=ReviewStatus.APPROVED.value,
                    )
                connection.commit()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể duyệt dịch vụ trong Service Catalog.") from exc
        return self._get_service_sync(service_id)

    def _set_withdrawn_sync(
        self,
        service_id: UUID,
        review_status: str | None,
        action: ReviewAction,
        actor: str,
        note: str | None,
    ) -> AdminServiceRecord | None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    current = self._locked_row(cursor, service_id)
                    if current is None:
                        return None
                    new_status = review_status or current.review_status
                    cursor.execute(
                        """
                        UPDATE services
                        SET active = FALSE,
                            review_status = %(review_status)s,
                            updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {"id": service_id, "review_status": new_status},
                    )
                    self._record_event(
                        cursor,
                        service_id=service_id,
                        action=action,
                        actor=actor,
                        note=note,
                        changed_fields=(
                            ("active", "review_status") if review_status else ("active",)
                        ),
                        previous_review_status=current.review_status,
                        new_review_status=new_status,
                    )
                connection.commit()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể rút dịch vụ khỏi Service Catalog.") from exc
        return self._get_service_sync(service_id)

    def _delete_service_sync(
        self,
        service_id: UUID,
        actor: str,
        note: str | None,
    ) -> AdminServiceRecord | None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    current = self._locked_row(cursor, service_id)
                    if current is None:
                        return None
                    if current.deleted_at is not None:
                        return current
                    # active is cleared in the same statement: the schema forbids a
                    # removed row from staying served, so this cannot be two steps.
                    cursor.execute(
                        """
                        UPDATE services
                        SET active = FALSE, deleted_at = now(), updated_at = now()
                        WHERE id = %s
                        """,
                        (service_id,),
                    )
                    self._record_event(
                        cursor,
                        service_id=service_id,
                        action=ReviewAction.DELETE,
                        actor=actor,
                        note=note,
                        changed_fields=(
                            ("active", "deleted_at") if current.active else ("deleted_at",)
                        ),
                        previous_review_status=current.review_status,
                        new_review_status=current.review_status,
                    )
                connection.commit()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể xóa dịch vụ khỏi Service Catalog.") from exc
        return self._get_service_sync(service_id)

    def _restore_service_sync(
        self,
        service_id: UUID,
        actor: str,
        note: str | None,
    ) -> AdminServiceRecord | None:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    current = self._locked_row(cursor, service_id)
                    if current is None:
                        return None
                    if current.deleted_at is None:
                        return current
                    # Restored rows stay unpublished; serving again is a separate,
                    # separately audited approval.
                    cursor.execute(
                        "UPDATE services SET deleted_at = NULL, updated_at = now() WHERE id = %s",
                        (service_id,),
                    )
                    self._record_event(
                        cursor,
                        service_id=service_id,
                        action=ReviewAction.RESTORE,
                        actor=actor,
                        note=note,
                        changed_fields=("deleted_at",),
                        previous_review_status=current.review_status,
                        new_review_status=current.review_status,
                    )
                connection.commit()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể phục hồi dịch vụ.") from exc
        return self._get_service_sync(service_id)

    def _find_by_launch_url_sync(self, launch_url: str) -> AdminServiceRecord | None:
        statement = f"SELECT {_ADMIN_DETAILS} FROM services AS s WHERE s.launch_url = %s LIMIT 1"
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, (launch_url,))
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể kiểm tra trùng launch URL.") from exc
        return self._row_to_record(row) if row is not None else None

    def _locked_row(
        self,
        cursor: psycopg.Cursor[dict[str, Any]],
        service_id: UUID,
    ) -> AdminServiceRecord | None:
        """Read a row inside the current transaction, locked against concurrent edits.

        The lock is taken by a bare statement rather than by adding ``FOR UPDATE`` to
        the detail query: the detail projection contains aggregating sub-selects, and
        keeping the locking clause on a plain single-table read avoids depending on how
        those interact with row locking.
        """

        cursor.execute("SELECT 1 FROM services WHERE id = %s FOR UPDATE", (service_id,))
        if cursor.fetchone() is None:
            return None
        cursor.execute(
            f"SELECT {_ADMIN_DETAILS} FROM services AS s WHERE s.id = %s",
            (service_id,),
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    @staticmethod
    def _replace_children(
        cursor: psycopg.Cursor[dict[str, Any]],
        service_id: UUID,
        aliases: Sequence[str],
        intents: Sequence[ServiceIntent],
    ) -> None:
        cursor.execute("DELETE FROM service_aliases WHERE service_id = %s", (service_id,))
        cursor.execute("DELETE FROM service_intents WHERE service_id = %s", (service_id,))
        cursor.executemany(
            "INSERT INTO service_aliases (service_id, alias) VALUES (%s, %s)",
            [(service_id, alias) for alias in dict.fromkeys(aliases)],
        )
        cursor.executemany(
            "INSERT INTO service_intents (service_id, intent, example_query) VALUES (%s, %s, %s)",
            [
                (service_id, intent.intent, intent.example_query)
                for intent in dict.fromkeys(intents)
            ],
        )

    @staticmethod
    def _record_event(
        cursor: psycopg.Cursor[dict[str, Any]],
        *,
        service_id: UUID,
        action: ReviewAction,
        actor: str,
        note: str | None,
        changed_fields: Sequence[str],
        previous_review_status: str | None,
        new_review_status: str | None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO service_review_events (
                service_id, action, actor, note, changed_fields,
                previous_review_status, new_review_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                service_id,
                action.value,
                actor,
                note,
                list(changed_fields),
                previous_review_status,
                new_review_status,
            ),
        )

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> AdminServiceRecord:
        intents = tuple(
            ServiceIntent(intent=str(item["intent"]), example_query=str(item["example_query"]))
            for item in row.get("intents") or ()
        )
        evidence = tuple(
            ServiceEvidence(
                source_url=str(item["source_url"]),
                publisher=_optional_text(item.get("publisher")),
                checked_at=(
                    datetime.fromisoformat(str(item["checked_at"]))
                    if item.get("checked_at")
                    else None
                ),
                verification_status=str(item.get("verification_status") or "candidate"),
                supports=_optional_text(item.get("supports")),
            )
            for item in row.get("evidence") or ()
        )
        return AdminServiceRecord(
            id=row["id"],
            name=str(row["name"]),
            provider=str(row["provider"]),
            service_type=ServiceType(str(row["service_type"])),
            category=str(row["category"]),
            description=str(row["description"]),
            launch_url=str(row["launch_url"]),
            owner=str(row["owner"]),
            active=bool(row["active"]),
            review_status=str(row["review_status"]),
            service_priority=int(row["service_priority"]),
            source_type=str(row["source_type"]),
            has_embedding=bool(row["has_embedding"]),
            region=_optional_text(row["region"]),
            target_user=_optional_text(row["target_user"]),
            organization=_optional_text(row["organization"]),
            last_verified_at=row["last_verified_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
            aliases=tuple(str(alias) for alias in row.get("aliases") or ()),
            intents=intents,
            evidence=evidence,
        )
