from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from domain.models import RegistryService, ServiceCategory, ServiceIntent, ServiceType
from domain.registry import ServiceRegistryRepository
from llm.embeddings import EmbeddingClient
from llm.schemas import StructuredQuery


class CatalogUnavailableError(RuntimeError):
    """The controlled PostgreSQL catalog cannot be queried safely."""


_PUBLISHED_STATUSES = ("approved", "published")
_SERVICE_DETAILS = """
    s.*,
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
    ), '[]'::jsonb) AS intents
"""


def _query_text(query: StructuredQuery) -> str:
    return " ".join(
        value
        for value in (
            query.service,
            query.intent,
            query.category,
            query.organization,
            query.location,
            query.target_user,
        )
        if value is not None and value.strip()
    )


def _vector_literal(vector: Sequence[float]) -> str:
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding must contain only finite values")
    return "[" + ",".join(format(value, ".8g") for value in vector) + "]"


class PostgresServiceRegistry(ServiceRegistryRepository):
    """PostgreSQL catalog with lexical, typo and optional vector candidate retrieval.

    Only records that are both active and approved/published are materialized as
    ``RegistryService``. Candidate research records can live in the same database
    but cannot appear in navigation responses.
    """

    def __init__(
        self,
        database_url: str,
        *,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        if not database_url.strip():
            raise ValueError("database_url cannot be empty for PostgreSQL search")
        self._database_url = database_url
        self._embedding_client = embedding_client

    async def list_active(self) -> tuple[RegistryService, ...]:
        return await asyncio.to_thread(self._list_active_sync)

    async def get_active(self, service_id: UUID) -> RegistryService | None:
        return await asyncio.to_thread(self._get_active_sync, service_id)

    async def search(self, query: StructuredQuery, limit: int = 10) -> list[RegistryService]:
        if limit <= 0 or query.out_of_scope or query.needs_clarification:
            return []

        text = _query_text(query)
        embedding: tuple[float, ...] | None = None
        if self._embedding_client is not None and text:
            embedding = await self._embedding_client.embed_query(text)
        return await asyncio.to_thread(self._search_sync, text, query.category, embedding, limit)

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        try:
            return psycopg.connect(
                self._database_url,
                connect_timeout=3,
                row_factory=dict_row,
            )
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể kết nối Service Catalog PostgreSQL.") from exc

    def _list_active_sync(self) -> tuple[RegistryService, ...]:
        statement = f"""
            SELECT {_SERVICE_DETAILS} FROM services AS s
            WHERE active = TRUE AND review_status = ANY(%s)
              AND service_type IN ('oa', 'mini_app')
            ORDER BY service_priority DESC, name ASC, id ASC
        """
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, (list(_PUBLISHED_STATUSES),))
                return tuple(self._row_to_service(row) for row in cursor.fetchall())
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể đọc Service Catalog PostgreSQL.") from exc

    def _get_active_sync(self, service_id: UUID) -> RegistryService | None:
        statement = f"""
            SELECT {_SERVICE_DETAILS} FROM services AS s
            WHERE id = %s AND active = TRUE AND review_status = ANY(%s)
              AND service_type IN ('oa', 'mini_app')
        """
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, (service_id, list(_PUBLISHED_STATUSES)))
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise CatalogUnavailableError("Không thể đọc Service Catalog PostgreSQL.") from exc
        return self._row_to_service(row) if row is not None else None

    def _search_sync(
        self,
        text: str,
        category: str | None,
        embedding: tuple[float, ...] | None,
        limit: int,
    ) -> list[RegistryService]:
        # RRF combines rankings instead of adding incompatible score scales.
        # Missing embeddings safely contribute zero semantic score.
        statement = f"""
            WITH input AS (
                SELECT websearch_to_tsquery('simple', %(text)s) AS tsq,
                       %(embedding)s::vector AS query_embedding
            ), scored AS (
                SELECT
                    {_SERVICE_DETAILS},
                    ts_rank_cd(s.search_vector, input.tsq) AS lexical_score,
                    GREATEST(
                        similarity(lower(s.name), lower(%(text)s)),
                        similarity(lower(s.search_text), lower(%(text)s)),
                        COALESCE((
                            SELECT max(similarity(lower(a.alias), lower(%(text)s)))
                            FROM service_aliases AS a
                            WHERE a.service_id = s.id
                        ), 0)
                    ) AS typo_score,
                    CASE
                        WHEN input.query_embedding IS NULL OR s.embedding IS NULL THEN 0
                        ELSE 1 - (s.embedding <=> input.query_embedding)
                    END AS semantic_score,
                    CASE
                        WHEN %(category)s::text IS NULL THEN 0
                        WHEN s.category = %(category)s::text THEN 1
                        ELSE 0
                    END AS category_score
                FROM services AS s
                CROSS JOIN input
                WHERE s.active = TRUE
                  AND s.review_status = ANY(%(published_statuses)s)
                  AND s.service_type IN ('oa', 'mini_app')
                  AND (%(category)s::text IS NULL OR s.category = %(category)s::text)
            ), ranked AS (
                SELECT
                    scored.*,
                    row_number() OVER (ORDER BY lexical_score DESC, id) AS lexical_rank,
                    row_number() OVER (ORDER BY typo_score DESC, id) AS typo_rank,
                    row_number() OVER (ORDER BY semantic_score DESC, id) AS semantic_rank
                FROM scored
            )
            SELECT * FROM ranked
            ORDER BY
                (1.0 / (60 + lexical_rank))
                + (1.0 / (60 + typo_rank))
                + CASE WHEN semantic_score > 0 THEN 1.0 / (60 + semantic_rank) ELSE 0 END
                + (category_score * 0.01)
                + (LEAST(GREATEST(service_priority, 0), 100) / 100000.0) DESC,
                name ASC,
                id ASC
            LIMIT %(limit)s
        """
        parameters = {
            "text": text,
            "embedding": _vector_literal(embedding) if embedding is not None else None,
            "category": category,
            "published_statuses": list(_PUBLISHED_STATUSES),
            "limit": limit,
        }
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                return [self._row_to_service(row) for row in cursor.fetchall()]
        except psycopg.Error as exc:
            raise CatalogUnavailableError(
                "Không thể tìm trong Service Catalog PostgreSQL."
            ) from exc

    @staticmethod
    def _row_to_service(row: dict[str, Any]) -> RegistryService:
        aliases = tuple(str(alias) for alias in row.get("aliases") or ())
        intents_value = row.get("intents") or ()
        intents = tuple(
            ServiceIntent(intent=str(item["intent"]), example_query=str(item["example_query"]))
            for item in intents_value
        )
        verified_at = row["last_verified_at"]
        if verified_at is not None and not isinstance(verified_at, datetime):
            raise CatalogUnavailableError("Service Catalog có last_verified_at không hợp lệ.")
        return RegistryService(
            id=row["id"],
            name=str(row["name"]),
            provider=str(row["provider"]),
            service_type=ServiceType(str(row["service_type"])),
            category=ServiceCategory(str(row["category"])),
            description=str(row["description"]),
            launch_url=str(row["launch_url"]),
            owner=str(row["owner"]),
            active=bool(row["active"]),
            service_priority=int(row["service_priority"]),
            region=str(row["region"]) if row["region"] is not None else None,
            target_user=str(row["target_user"]) if row["target_user"] is not None else None,
            organization=str(row["organization"]) if row["organization"] is not None else None,
            last_verified_at=verified_at,
            aliases=aliases,
            intents=intents,
        )
