#!/usr/bin/env python3
"""Import reviewed registry and optional research candidates into PostgreSQL.

Candidates are intentionally imported as ``active=false`` and ``candidate``. They
remain searchable for internal research only and cannot be returned by /navigate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "registry" / "services.real.json"
CANDIDATES_PATH = ROOT / "data" / "research" / "oa-candidates.json"
APPROVED_CANDIDATES_PATH = ROOT / "data" / "registry" / "approved-candidate-ids.json"

# Import the runtime enum rather than restating the category list, so the seeder and
# the navigator cannot drift apart. The path insert lets the script run from the repo
# root on a host that has not exported PYTHONPATH=src.
sys.path.insert(0, str(ROOT / "src"))

from domain.models import ServiceCategory  # noqa: E402

_VALID_CATEGORIES = frozenset(item.value for item in ServiceCategory)


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--include-candidates", action="store_true")
    parser.add_argument(
        "--approved-candidates-path",
        type=Path,
        default=APPROVED_CANDIDATES_PATH,
        help="Manifest candidate OA/Mini App được phép publish.",
    )
    parser.add_argument(
        "--embed", action="store_true", help="Tạo embedding qua Gemini cho record import."
    )
    parser.add_argument(
        "--embedding-model", default=os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
    )
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=int(os.environ.get("EMBEDDING_DIMENSIONS", "768")),
    )
    return parser.parse_args()


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def joined_text(record: Mapping[str, object]) -> str:
    aliases = record.get("aliases") or []
    intents = record.get("intents") or []
    intent_text: list[str] = []
    for item in intents:
        if isinstance(item, Mapping):
            intent_text.append(str(item.get("intent", "")))
            examples = item.get("example_queries", item.get("example_query", []))
            if isinstance(examples, str):
                intent_text.append(examples)
            elif isinstance(examples, Iterable):
                intent_text.extend(str(value) for value in examples)
    values = [
        str(record.get("name", "")),
        str(record.get("provider", "")),
        str(record.get("category", "")),
        str(record.get("description", "")),
        str(record.get("region", "")),
        str(record.get("target_user", "")),
        str(record.get("organization", "")),
        *(str(value) for value in aliases),
        *intent_text,
    ]
    return " ".join(value.strip() for value in values if value and value.strip())


def candidate_uuid(candidate_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"zalo-service-navigator:candidate:{candidate_id}")


def parse_verified_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def candidate_verified_at(record: Mapping[str, object]) -> datetime | None:
    evidence = record.get("evidence")
    if not isinstance(evidence, Iterable) or isinstance(evidence, (str, bytes, Mapping)):
        return None
    checked_dates = [
        item.get("checked_at")
        for item in evidence
        if isinstance(item, Mapping) and isinstance(item.get("checked_at"), str)
    ]
    if not checked_dates:
        return None
    return datetime.fromisoformat(max(str(value) for value in checked_dates)).replace(tzinfo=UTC)


def approved_candidate_ids(path: Path) -> frozenset[str]:
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise SystemExit("Approved candidate manifest không hợp lệ.")
    candidate_ids = payload.get("approved_candidate_ids")
    if not isinstance(candidate_ids, list) or not all(
        isinstance(candidate_id, str) and candidate_id.strip() for candidate_id in candidate_ids
    ):
        raise SystemExit("approved_candidate_ids phải là danh sách string không rỗng.")
    normalized = frozenset(candidate_id.strip() for candidate_id in candidate_ids)
    if len(normalized) != len(candidate_ids):
        raise SystemExit("Approved candidate manifest có candidate_id trùng.")
    return normalized


def as_text(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        joined = ", ".join(str(item).strip() for item in value if str(item).strip())
        return joined or None
    return None


def as_intents(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return []
    results: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        intent = item.get("intent")
        examples = item.get("example_queries", item.get("example_query", []))
        if not isinstance(intent, str) or not intent.strip():
            continue
        if isinstance(examples, str):
            examples = [examples]
        if not isinstance(examples, Iterable) or isinstance(examples, (bytes, Mapping)):
            continue
        for example in examples:
            if isinstance(example, str) and example.strip():
                results.append((intent.strip(), example.strip()))
    return results


def embed_document(
    client: genai.Client | None,
    text: str,
    *,
    model: str,
    dimensions: int,
) -> list[float] | None:
    if client is None:
        return None
    response = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=dimensions,
        ),
    )
    values = response.embeddings[0].values if response.embeddings else None
    if values is None or len(values) != dimensions:
        raise ValueError("Gemini trả embedding không đúng kích thước.")
    return [float(value) for value in values]


EvidenceRow = tuple[str, str | None, datetime | None, str, str | None]


def evidence_rows(record: Mapping[str, object]) -> list[EvidenceRow]:
    """Flatten a record's research evidence into ``service_evidence`` rows.

    The ``supports`` claims are joined into one block so the review console can show
    why each source counts, and ``verification_status`` reflects the record-level
    verdict because the source entries themselves carry no status of their own.
    """

    evidence = record.get("evidence")
    if not isinstance(evidence, Iterable) or isinstance(evidence, (str, bytes, Mapping)):
        return []
    verification = record.get("verification")
    official = isinstance(verification, Mapping) and verification.get("official_source") is True
    status = "official_source" if official else "candidate"

    rows: list[EvidenceRow] = []
    seen: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url", "")).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        supports = item.get("supports")
        if isinstance(supports, str):
            supports_text: str | None = supports.strip() or None
        elif isinstance(supports, Iterable) and not isinstance(supports, (bytes, Mapping)):
            joined = "\n".join(str(value).strip() for value in supports if str(value).strip())
            supports_text = joined or None
        else:
            supports_text = None
        checked_at = item.get("checked_at")
        checked = (
            datetime.fromisoformat(str(checked_at)).replace(tzinfo=UTC)
            if isinstance(checked_at, str) and checked_at.strip()
            else None
        )
        rows.append((url, as_text(item.get("publisher")), checked, status, supports_text))
    return rows


def validated_category(record: Mapping[str, object], service_id: UUID) -> str:
    """Return the record's category, refusing values the runtime cannot represent.

    ``PostgresServiceRegistry`` coerces this column through ``ServiceCategory``, so a
    value outside that enum produces a row the navigator has to skip. Defaulting to a
    placeholder like ``uncategorized`` imported exactly such a row silently, so a
    missing or unknown category now stops the import instead.
    """

    raw = record.get("category")
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit(
            f"{service_id}: thiếu trường category. "
            f"Giá trị hợp lệ: {', '.join(sorted(_VALID_CATEGORIES))}."
        )
    category = raw.strip().casefold()
    if category not in _VALID_CATEGORIES:
        raise SystemExit(
            f"{service_id}: category {raw!r} nằm ngoài danh mục runtime. "
            f"Giá trị hợp lệ: {', '.join(sorted(_VALID_CATEGORIES))}."
        )
    return category


def upsert_record(
    connection: psycopg.Connection[tuple[object, ...]],
    record: Mapping[str, object],
    *,
    service_id: UUID,
    source_type: str,
    embedding: list[float] | None,
    publish_candidate: bool = False,
) -> None:
    aliases = [str(value).strip() for value in record.get("aliases", []) if str(value).strip()]
    intents = as_intents(record.get("intents"))
    active = (bool(record.get("active", False)) and source_type == "registry") or publish_candidate
    review_status = "approved" if active else str(record.get("review_status", "candidate"))
    service_type = str(record.get("service_type", record.get("channel_type", "oa")))
    launch_url = str(record.get("launch_url", ""))
    search_text = joined_text(record)
    category = validated_category(record, service_id)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO services (
                id, name, provider, service_type, category, description, launch_url,
                owner, active, review_status, service_priority, region, target_user,
                organization, last_verified_at, search_text, embedding, source_type
            ) VALUES (
                %(id)s, %(name)s, %(provider)s, %(service_type)s, %(category)s, %(description)s,
                %(launch_url)s, %(owner)s, %(active)s, %(review_status)s, %(service_priority)s,
                %(region)s, %(target_user)s, %(organization)s, %(last_verified_at)s,
                %(search_text)s, %(embedding)s::vector, %(source_type)s
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                provider = EXCLUDED.provider,
                service_type = EXCLUDED.service_type,
                category = EXCLUDED.category,
                description = EXCLUDED.description,
                launch_url = EXCLUDED.launch_url,
                owner = EXCLUDED.owner,
                active = EXCLUDED.active,
                review_status = EXCLUDED.review_status,
                service_priority = EXCLUDED.service_priority,
                region = EXCLUDED.region,
                target_user = EXCLUDED.target_user,
                organization = EXCLUDED.organization,
                last_verified_at = EXCLUDED.last_verified_at,
                search_text = EXCLUDED.search_text,
                embedding = COALESCE(EXCLUDED.embedding, services.embedding),
                source_type = EXCLUDED.source_type,
                updated_at = now()
            """,
            {
                "id": service_id,
                "name": str(record["name"]),
                "provider": str(record.get("provider", "Unknown")),
                "service_type": service_type,
                "category": category,
                "description": str(record.get("description", "No description")),
                "launch_url": launch_url,
                "owner": str(record.get("owner", "research")),
                "active": active,
                "review_status": review_status,
                "service_priority": int(record.get("service_priority", 0)),
                "region": as_text(record.get("region", record.get("regions"))),
                "target_user": as_text(record.get("target_user", record.get("target_users"))),
                "organization": as_text(
                    record.get("organization", record.get("organization_contexts"))
                ),
                "last_verified_at": (
                    parse_verified_at(record.get("last_verified_at"))
                    or (candidate_verified_at(record) if publish_candidate else None)
                ),
                "search_text": search_text,
                "embedding": (
                    "[" + ",".join(format(value, ".8g") for value in embedding) + "]"
                    if embedding is not None
                    else None
                ),
                "source_type": source_type,
            },
        )
        cursor.execute("DELETE FROM service_aliases WHERE service_id = %s", (service_id,))
        cursor.execute("DELETE FROM service_intents WHERE service_id = %s", (service_id,))
        cursor.execute("DELETE FROM service_evidence WHERE service_id = %s", (service_id,))
        cursor.executemany(
            "INSERT INTO service_aliases (service_id, alias) VALUES (%s, %s)",
            [(service_id, alias) for alias in aliases],
        )
        cursor.executemany(
            "INSERT INTO service_intents (service_id, intent, example_query) VALUES (%s, %s, %s)",
            [(service_id, intent, example) for intent, example in intents],
        )
        cursor.executemany(
            """
            INSERT INTO service_evidence (
                service_id, source_url, publisher, checked_at, verification_status, supports
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [(service_id, *row) for row in evidence_rows(record)],
        )


def main() -> int:
    configure_utf8_output()
    args = parse_args()
    if not args.database_url.strip():
        raise SystemExit("DATABASE_URL là bắt buộc.")
    if args.embedding_dimensions != 768:
        raise SystemExit(
            "Schema PostgreSQL hiện dùng vector(768); EMBEDDING_DIMENSIONS phải là 768."
        )
    registry_payload = read_json(REGISTRY_PATH)
    if not isinstance(registry_payload, Mapping):
        raise SystemExit("Registry JSON không hợp lệ.")
    registry_records = registry_payload.get("services")
    if not isinstance(registry_records, list):
        raise SystemExit("Registry không có danh sách services.")

    approved_ids = approved_candidate_ids(args.approved_candidates_path)
    client: genai.Client | None = None
    if args.embed:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("--embed yêu cầu GEMINI_API_KEY.")
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1"})

    imported_urls: set[str] = set()
    count = 0
    with psycopg.connect(args.database_url) as connection:
        for record in registry_records:
            if not isinstance(record, Mapping):
                continue
            if str(record.get("service_type", "")) not in {"oa", "mini_app"}:
                continue
            service_id = UUID(str(record["id"]))
            text = joined_text(record)
            upsert_record(
                connection,
                record,
                service_id=service_id,
                source_type="registry",
                embedding=embed_document(
                    client, text, model=args.embedding_model, dimensions=args.embedding_dimensions
                ),
            )
            imported_urls.add(str(record.get("launch_url", "")))
            count += 1

        if args.include_candidates:
            candidates_payload = read_json(CANDIDATES_PATH)
            candidates = (
                candidates_payload.get("services", [])
                if isinstance(candidates_payload, Mapping)
                else []
            )
            for record in candidates:
                if not isinstance(record, Mapping) or not isinstance(
                    record.get("candidate_id"), str
                ):
                    continue
                if str(record.get("channel_type", "")) not in {"oa", "mini_app"}:
                    continue
                if str(record.get("launch_url", "")) in imported_urls:
                    continue
                text = joined_text(record)
                candidate_id = str(record["candidate_id"])
                publish_candidate = candidate_id in approved_ids
                if publish_candidate:
                    verification = record.get("verification")
                    if not isinstance(verification, Mapping) or not (
                        verification.get("confidence") in {"high", "medium"}
                        and verification.get("official_source") is True
                        and verification.get("link_reachable") is True
                    ):
                        raise SystemExit(
                            f"{candidate_id}: manifest chỉ được publish OA/Mini App "
                            "medium/high có nguồn chính chủ và link hoạt động."
                        )
                upsert_record(
                    connection,
                    record,
                    service_id=candidate_uuid(candidate_id),
                    source_type="research",
                    embedding=embed_document(
                        client,
                        text,
                        model=args.embedding_model,
                        dimensions=args.embedding_dimensions,
                    ),
                    publish_candidate=publish_candidate,
                )
                count += 1
    print(f"Đã import {count} service vào PostgreSQL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
