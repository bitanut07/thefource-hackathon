from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from domain.models import ServiceType
from domain.search import LaunchUrlPolicy
from domain.urls import is_canonical_zalo_oa_url

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_LAUNCHABLE_REVIEW_STATUSES = frozenset({"active", "approved", "published"})
_LAUNCHABLE_VERIFICATION_STATUSES = frozenset({"official_verified", "verified", "verified_high"})
_NON_LAUNCHABLE_SOURCE_TYPES = frozenset(
    {
        "campus_amenity_fact",
        "public_zalo_mini_app_reference",
        "user_reported",
    }
)


def normalize_search_text(value: str) -> str:
    """Return stable, accent-insensitive text suitable for lexical search."""

    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_TOKEN_PATTERN.findall(without_marks))


@dataclass(frozen=True, slots=True)
class RagDocument:
    document_id: str
    name: str
    content: str
    source_path: str
    source_type: str
    category: str | None = None
    channel_type: str | None = None
    launch_url: str | None = None
    official_url: str | None = None
    active: bool = False
    launchable: bool = False
    review_status: str = "knowledge_only"
    verification_status: str = "unverified"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        for field_name in ("document_id", "name", "content", "source_path", "source_type"):
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not self.launchable:
            return
        if not self.active:
            raise ValueError("a launchable RAG document must be active")
        if self.launch_url is None or not self.launch_url.strip():
            raise ValueError("a launchable RAG document must have a launch URL")
        if self.source_type in _NON_LAUNCHABLE_SOURCE_TYPES:
            raise ValueError(f"{self.source_type!r} documents are knowledge-only")
        if self.review_status.strip().casefold() not in _LAUNCHABLE_REVIEW_STATUSES:
            raise ValueError(f"{self.review_status!r} review status is not launchable")
        if self.verification_status.strip().casefold() not in _LAUNCHABLE_VERIFICATION_STATUSES:
            raise ValueError(f"{self.verification_status!r} verification status is not launchable")
        if self.channel_type == ServiceType.OA.value and not is_canonical_zalo_oa_url(
            self.launch_url
        ):
            raise ValueError("a launchable OA document must use https://zalo.me/<numeric-oa-id>")


@dataclass(frozen=True, slots=True)
class RagSearchResult:
    document: RagDocument
    score: float
    matched_terms: tuple[str, ...]


class SqliteRagStore:
    """Small deterministic RAG catalog backed by SQLite.

    FTS5 is used to prune candidates when the local SQLite build supports it.
    Results are always scored in Python, so ordering stays consistent with the
    portable full-table lexical fallback.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        prefer_fts: bool = True,
        allowed_launch_hosts: frozenset[str] = frozenset(),
    ) -> None:
        self.path = Path(path) if path != ":memory:" else Path(":memory:")
        self._launch_url_policy = LaunchUrlPolicy(allowed_launch_hosts)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._fts_enabled = prefer_fts and self._create_fts_schema()

    @property
    def fts_enabled(self) -> bool:
        return self._fts_enabled

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SqliteRagStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_documents (
                document_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_type TEXT NOT NULL,
                category TEXT,
                channel_type TEXT,
                launch_url TEXT,
                official_url TEXT,
                active INTEGER NOT NULL CHECK (active IN (0, 1)),
                launchable INTEGER NOT NULL CHECK (launchable IN (0, 1)),
                review_status TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                CHECK (launchable = 0 OR (active = 1 AND launch_url IS NOT NULL))
            );

            CREATE INDEX IF NOT EXISTS idx_rag_documents_source
                ON rag_documents(source_type, verification_status);
            CREATE INDEX IF NOT EXISTS idx_rag_documents_launchable
                ON rag_documents(launchable);
            """
        )
        self._connection.commit()

    def _create_fts_schema(self) -> bool:
        try:
            self._connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_documents_fts
                USING fts5(
                    document_id UNINDEXED,
                    name,
                    normalized_text,
                    tokenize = 'unicode61 remove_diacritics 2'
                )
                """
            )
            document_count = int(
                self._connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0]
            )
            fts_count = int(
                self._connection.execute("SELECT COUNT(*) FROM rag_documents_fts").fetchone()[0]
            )
            if document_count != fts_count:
                # A database can be built on a SQLite runtime without FTS5 and
                # later opened where FTS5 is available. Populate the newly
                # created index before allowing reads to use it.
                self._connection.execute("DELETE FROM rag_documents_fts")
                self._connection.execute(
                    """
                    INSERT INTO rag_documents_fts (
                        document_id, name, normalized_text
                    )
                    SELECT document_id, normalized_name, normalized_text
                    FROM rag_documents
                    """
                )
            self._connection.commit()
        except sqlite3.OperationalError:
            self._connection.rollback()
            return False
        return True

    def replace_documents(self, documents: Iterator[RagDocument] | list[RagDocument]) -> int:
        materialized = list(documents)
        seen_ids: set[str] = set()
        for document in materialized:
            document.validate()
            if document.launchable and not self._is_launchable_allowed(document):
                raise ValueError(
                    "a launchable RAG document must use HTTPS and an explicitly allowed host"
                )
            if document.document_id in seen_ids:
                raise ValueError(f"duplicate RAG document id: {document.document_id}")
            seen_ids.add(document.document_id)

        with self._connection:
            if self._fts_enabled:
                self._connection.execute("DELETE FROM rag_documents_fts")
            self._connection.execute("DELETE FROM rag_documents")
            for document in materialized:
                normalized_name = normalize_search_text(document.name)
                normalized_text = normalize_search_text(
                    " ".join(
                        part
                        for part in (
                            document.name,
                            document.content,
                            document.category,
                            document.channel_type,
                            document.review_status,
                            document.verification_status,
                        )
                        if part
                    )
                )
                metadata_json = json.dumps(
                    document.metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self._connection.execute(
                    """
                    INSERT INTO rag_documents (
                        document_id, name, content, normalized_name, normalized_text,
                        source_path, source_type, category, channel_type, launch_url,
                        official_url, active, launchable, review_status,
                        verification_status, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.document_id,
                        document.name,
                        document.content,
                        normalized_name,
                        normalized_text,
                        document.source_path,
                        document.source_type,
                        document.category,
                        document.channel_type,
                        document.launch_url,
                        document.official_url,
                        int(document.active),
                        int(document.launchable),
                        document.review_status,
                        document.verification_status,
                        metadata_json,
                    ),
                )
                if self._fts_enabled:
                    self._connection.execute(
                        """
                        INSERT INTO rag_documents_fts (
                            document_id, name, normalized_text
                        ) VALUES (?, ?, ?)
                        """,
                        (document.document_id, normalized_name, normalized_text),
                    )
        return len(materialized)

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM rag_documents").fetchone()
        return int(row["count"]) if row is not None else 0

    def get(self, document_id: str) -> RagDocument | None:
        row = self._connection.execute(
            "SELECT * FROM rag_documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        return self._document_from_row(row) if row is not None else None

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        launchable_only: bool = False,
        category: str | None = None,
    ) -> list[RagSearchResult]:
        if limit <= 0:
            return []

        normalized_query = normalize_search_text(query)
        query_terms = tuple(dict.fromkeys(normalized_query.split()))
        if not query_terms:
            return []

        rows = self._candidate_rows(
            query_terms,
            launchable_only=launchable_only,
            category=category,
            candidate_limit=max(limit * 20, 200),
        )
        results: list[RagSearchResult] = []
        for row in rows:
            normalized_text = str(row["normalized_text"])
            text_terms = set(normalized_text.split())
            matched_terms = tuple(term for term in query_terms if term in text_terms)
            if not matched_terms:
                continue

            document = self._document_from_row(row)
            if launchable_only and not self._is_launchable_allowed(document):
                continue
            score = _lexical_score(
                normalized_query=normalized_query,
                query_terms=query_terms,
                matched_terms=matched_terms,
                normalized_name=str(row["normalized_name"]),
                normalized_text=normalized_text,
            )
            results.append(
                RagSearchResult(
                    document=document,
                    score=score,
                    matched_terms=matched_terms,
                )
            )

        results.sort(
            key=lambda result: (
                -result.score,
                normalize_search_text(result.document.name),
                result.document.document_id,
            )
        )
        return results[:limit]

    def _is_launchable_allowed(self, document: RagDocument) -> bool:
        if not document.launchable or document.launch_url is None:
            return False
        try:
            document.validate()
        except ValueError:
            return False
        if document.channel_type == ServiceType.OA.value:
            return self._launch_url_policy.is_allowed_for_service(
                ServiceType.OA,
                document.launch_url,
            )
        return self._launch_url_policy.is_allowed(document.launch_url)

    def _candidate_rows(
        self,
        query_terms: tuple[str, ...],
        *,
        launchable_only: bool,
        category: str | None,
        candidate_limit: int,
    ) -> list[sqlite3.Row]:
        if self._fts_enabled:
            # Tokens come exclusively from ``normalize_search_text``. Quoting each
            # token additionally prevents user input from becoming FTS syntax.
            fts_query = " OR ".join(f'"{term}"' for term in query_terms)
            conditions = ["rag_documents_fts MATCH ?"]
            parameters: list[object] = [fts_query]
            if launchable_only:
                conditions.append("d.launchable = 1")
            if category is not None:
                conditions.append("d.category = ?")
                parameters.append(category)
            parameters.append(candidate_limit)
            return list(
                self._connection.execute(
                    f"""
                    SELECT d.*
                    FROM rag_documents_fts AS f
                    JOIN rag_documents AS d ON d.document_id = f.document_id
                    WHERE {" AND ".join(conditions)}
                    ORDER BY d.document_id
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
            )

        conditions = []
        parameters = []
        if launchable_only:
            conditions.append("launchable = 1")
        if category is not None:
            conditions.append("category = ?")
            parameters.append(category)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return list(
            self._connection.execute(
                f"""
                SELECT *
                FROM rag_documents
                {where_sql}
                ORDER BY document_id
                """,
                parameters,
            ).fetchall()
        )

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> RagDocument:
        raw_metadata = json.loads(str(row["metadata_json"]))
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        return RagDocument(
            document_id=str(row["document_id"]),
            name=str(row["name"]),
            content=str(row["content"]),
            source_path=str(row["source_path"]),
            source_type=str(row["source_type"]),
            category=str(row["category"]) if row["category"] is not None else None,
            channel_type=(str(row["channel_type"]) if row["channel_type"] is not None else None),
            launch_url=str(row["launch_url"]) if row["launch_url"] is not None else None,
            official_url=str(row["official_url"]) if row["official_url"] is not None else None,
            active=bool(row["active"]),
            launchable=bool(row["launchable"]),
            review_status=str(row["review_status"]),
            verification_status=str(row["verification_status"]),
            metadata=metadata,
        )


def _lexical_score(
    *,
    normalized_query: str,
    query_terms: tuple[str, ...],
    matched_terms: tuple[str, ...],
    normalized_name: str,
    normalized_text: str,
) -> float:
    coverage = len(matched_terms) / len(query_terms)
    name_terms = set(normalized_name.split())
    name_coverage = len(set(query_terms) & name_terms) / len(query_terms)
    phrase_match = float(normalized_query in normalized_text)
    exact_name = float(normalized_query == normalized_name)
    score = (0.65 * coverage) + (0.20 * name_coverage) + (0.10 * phrase_match)
    score += 0.05 * exact_name
    return round(score, 6)
