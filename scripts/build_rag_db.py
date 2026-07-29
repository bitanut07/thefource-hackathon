from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from domain.rag_store import RagDocument, SqliteRagStore  # noqa: E402

DEFAULT_CATALOG = ROOT / "data" / "research" / "oa-candidates.json"
DEFAULT_PENDING = ROOT / "data" / "research" / "pending" / "vng-campus-food.json"
DEFAULT_OUTPUT = ROOT / "data" / "rag" / "service-catalog.sqlite3"


def _read_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return cast(dict[str, object], payload)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _flatten_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten_values(item)


def _content(*values: object) -> str:
    parts = (part.strip() for value in values for part in _flatten_values(value) if part.strip())
    return "\n".join(parts)


def catalog_documents(path: Path) -> list[RagDocument]:
    payload = _read_object(path)
    services = _mapping_list(payload.get("services"))
    documents: list[RagDocument] = []
    for service in services:
        channel_type = str(service.get("channel_type", "")).strip()
        # The Navigator catalog is Zalo-native. Keep raw website research in
        # the JSON evidence archive, but never index it for API/RAG search.
        if channel_type not in {"oa", "mini_app"}:
            continue
        candidate_id = str(service.get("candidate_id", "")).strip()
        if not candidate_id:
            raise ValueError(f"{path}: catalog service is missing candidate_id")

        verification = _mapping(service.get("verification"))
        confidence = str(verification.get("confidence", "unverified"))
        review_status = str(service.get("review_status", "candidate"))
        active = service.get("active") is True
        launch_url = service.get("launch_url")
        launch_url_text = launch_url if isinstance(launch_url, str) else None
        # Research candidates remain knowledge until an explicit approval step
        # changes both their active and review states.
        launchable = bool(
            active
            and launch_url_text
            and review_status in {"active", "approved"}
            and confidence == "high"
        )
        documents.append(
            RagDocument(
                document_id=f"catalog:{candidate_id}",
                name=str(service.get("name", candidate_id)),
                content=_content(
                    service.get("name"),
                    service.get("provider"),
                    service.get("description"),
                    service.get("category"),
                    service.get("subcategory"),
                    service.get("regions"),
                    service.get("target_users"),
                    service.get("capabilities"),
                    service.get("aliases"),
                    service.get("intents"),
                    service.get("organization_contexts"),
                    service.get("evidence"),
                ),
                source_path=path.as_posix(),
                source_type="public_first_party_catalog",
                category=(
                    str(service["category"]) if isinstance(service.get("category"), str) else None
                ),
                channel_type=(channel_type),
                launch_url=launch_url_text,
                official_url=(
                    str(service["official_website"])
                    if isinstance(service.get("official_website"), str)
                    else None
                ),
                active=active,
                launchable=launchable,
                review_status=review_status,
                verification_status=("verified_high" if launchable else f"candidate_{confidence}"),
                metadata=dict(service),
            )
        )
    return documents


def pending_documents(path: Path) -> list[RagDocument]:
    payload = _read_object(path)
    scope = _mapping(payload.get("scope"))
    official_context = _mapping(payload.get("official_context"))
    shared_context = _content(
        "VNG VNG Campus nhân viên VNG Starter VNG",
        "đồ ăn thức uống ăn trưa quán ăn quán nước canteen căng tin",
        scope,
    )
    documents: list[RagDocument] = []

    if official_context:
        record_type = str(official_context.get("record_type", "campus_amenity_fact"))
        documents.append(
            RagDocument(
                document_id="pending:vng-campus-food-amenities",
                name="Tiện ích ăn uống tại VNG Campus",
                content=_content(shared_context, official_context),
                source_path=path.as_posix(),
                source_type=record_type,
                category="shopping_delivery",
                active=False,
                launchable=False,
                review_status="knowledge_only",
                verification_status="verified_context_only",
                metadata=dict(official_context),
            )
        )

    for candidate in _mapping_list(payload.get("user_reported_candidates")):
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        if not candidate_id:
            raise ValueError(f"{path}: user-reported candidate is missing candidate_id")
        documents.append(
            RagDocument(
                document_id=f"pending:{candidate_id}",
                name=str(candidate.get("name", candidate_id)),
                content=_content(
                    shared_context,
                    "Tên nhà cung cấp do người dùng báo cáo; chưa xác minh hiện diện tại Campus.",
                    candidate,
                ),
                source_path=path.as_posix(),
                source_type="user_reported",
                category="shopping_delivery",
                channel_type=(
                    str(candidate["channel_type"])
                    if isinstance(candidate.get("channel_type"), str)
                    else None
                ),
                active=False,
                launchable=False,
                review_status=str(candidate.get("review_status", "pending_verification")),
                verification_status=str(candidate.get("verification_status", "needs_official_url")),
                metadata=dict(candidate),
            )
        )

    for reference in _mapping_list(payload.get("public_mini_app_references")):
        reference_id = str(reference.get("reference_id", "")).strip()
        if not reference_id:
            raise ValueError(f"{path}: Mini App reference is missing reference_id")
        launch_url = reference.get("launch_url")
        documents.append(
            RagDocument(
                document_id=f"pending:{reference_id}",
                name=str(reference.get("name", reference_id)),
                content=_content(
                    shared_context,
                    "Mini App công khai; hiện diện và khả năng đặt món "
                    "tại VNG Campus chưa xác minh.",
                    reference,
                ),
                source_path=path.as_posix(),
                source_type="public_zalo_mini_app_reference",
                category="shopping_delivery",
                channel_type=(
                    str(reference["channel_type"])
                    if isinstance(reference.get("channel_type"), str)
                    else None
                ),
                launch_url=launch_url if isinstance(launch_url, str) else None,
                active=False,
                launchable=False,
                review_status=str(reference.get("review_status", "reference_only")),
                verification_status="unverified",
                metadata=dict(reference),
            )
        )
    return documents


def build_database(
    *,
    catalog_path: Path,
    pending_path: Path,
    output_path: Path,
    allowed_launch_hosts: frozenset[str] = frozenset(),
) -> int:
    documents = [*catalog_documents(catalog_path), *pending_documents(pending_path)]
    with SqliteRagStore(
        output_path,
        allowed_launch_hosts=allowed_launch_hosts,
    ) as store:
        return store.replace_documents(documents)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local SQLite RAG service catalog.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allowed-launch-hosts",
        default="",
        help="Comma-separated exact hosts allowed for approved launchable RAG records.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = build_database(
        catalog_path=args.catalog.resolve(),
        pending_path=args.pending.resolve(),
        output_path=args.output.resolve(),
        allowed_launch_hosts=frozenset(
            host.strip() for host in args.allowed_launch_hosts.split(",") if host.strip()
        ),
    )
    print(f"Indexed {count} RAG documents in {args.output.resolve()}")


if __name__ == "__main__":
    main()
