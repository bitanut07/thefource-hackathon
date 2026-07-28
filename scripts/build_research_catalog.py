from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from domain.urls import is_canonical_zalo_oa_url

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "research" / "raw"
OUTPUT = ROOT / "data" / "research" / "oa-candidates.json"
GENERATED_AT = "2026-07-24T00:00:00+07:00"

CATEGORIES = {
    "food",
    "education",
    "shopping",
    "finance",
    "utilities",
    "health",
    "government",
    "other",
}
_CATEGORY_MAP = {
    "education": "education",
    "finance_banking": "finance",
    "healthcare": "health",
    "public_admin": "government",
    "utilities": "utilities",
    # Zalo's supplied taxonomy has no travel or entertainment bucket. Keep a
    # visible extension rather than incorrectly classifying them as All.
    "transport_travel": "other",
    "entertainment": "other",
}
_FOOD_SUBCATEGORY_TERMS = frozenset(
    {
        "bakery",
        "banh_mi",
        "bbq",
        "beverage",
        "bubble_tea",
        "buffet",
        "cafe",
        "cake",
        "chocolate",
        "coffee",
        "drink",
        "fast_food",
        "fried_chicken",
        "hotpot",
        "pizza",
        "restaurant",
        "rice",
        "vegetarian",
    }
)
CHANNEL_TYPES = {"oa", "mini_app", "website", "unknown"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
BADGE_STATUSES = {"verified", "not_verified", "unknown", "not_applicable"}
ORGANIZATION_RELATIONSHIPS = {"employee_service", "onsite", "nearby"}
ACCESS_SCOPES = {"employees_only", "public", "unknown"}
CONTEXT_VERIFICATION_STATUSES = {"verified", "user_reported", "historical", "unverified"}
CANDIDATE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return cast(list[dict[str, Any]], payload)
    if isinstance(payload, dict) and isinstance(payload.get("services"), list):
        return cast(list[dict[str, Any]], payload["services"])
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return cast(list[dict[str, Any]], payload["records"])
    raise ValueError(f"{path}: expected a JSON list or an object with services[]/records[]")


def is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize(record: dict[str, Any]) -> dict[str, Any]:
    item = dict(record)
    candidate_id = item.get("candidate_id")
    if isinstance(candidate_id, str):
        item["candidate_id"] = candidate_id.replace("_", "-")

    source_category = item.get("category")
    if isinstance(source_category, str):
        item["internal_category"] = source_category
        if source_category == "shopping_delivery":
            subcategory = str(item.get("subcategory", "")).casefold()
            item["category"] = (
                "food"
                if any(term in subcategory for term in _FOOD_SUBCATEGORY_TERMS)
                else "shopping"
            )
        else:
            item["category"] = _CATEGORY_MAP.get(source_category, "other")

    channel_type = item.get("channel_type", "unknown")
    item.setdefault("logo_url", None)
    item.setdefault("logo_usage", "reference_only_needs_review")
    item.setdefault("cta_label", "Mở OA" if channel_type == "oa" else "Mở dịch vụ")
    item.setdefault("official_website", None)
    item.setdefault("organization_contexts", [])

    evidence_items: list[dict[str, Any]] = []
    for raw_evidence in item.get("evidence") or []:
        evidence = dict(raw_evidence)
        supports = evidence.get("supports")
        if isinstance(supports, str):
            evidence["supports"] = [supports]
        evidence_items.append(evidence)
    item["evidence"] = evidence_items

    verification = dict(item.get("verification") or {})
    verification.setdefault(
        "oa_badge_status", "unknown" if channel_type == "oa" else "not_applicable"
    )
    verification.setdefault("cross_linked", None)
    verification.setdefault("notes", "")
    item["verification"] = verification
    return item


def validate(item: dict[str, Any], origin: Path) -> list[str]:
    errors: list[str] = []
    candidate_id = item.get("candidate_id")
    prefix = f"{origin.name}:{candidate_id or '<missing-id>'}"

    required_strings = (
        "candidate_id",
        "name",
        "provider",
        "subcategory",
        "description",
        "cta_label",
    )
    for field in required_strings:
        if not isinstance(item.get(field), str) or not item[field].strip():
            errors.append(f"{prefix}: {field} must be a non-empty string")

    if isinstance(candidate_id, str) and not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        errors.append(f"{prefix}: candidate_id must use lowercase kebab-case")
    if item.get("category") not in CATEGORIES:
        errors.append(f"{prefix}: unsupported category {item.get('category')!r}")
    if item.get("channel_type") not in CHANNEL_TYPES:
        errors.append(f"{prefix}: unsupported channel_type {item.get('channel_type')!r}")
    if isinstance(item.get("description"), str) and len(item["description"]) > 360:
        errors.append(f"{prefix}: description exceeds 360 characters")
    if not is_http_url(item.get("launch_url")):
        errors.append(f"{prefix}: launch_url must be an HTTP(S) URL")
    elif item.get("channel_type") == "oa" and not is_canonical_zalo_oa_url(item["launch_url"]):
        errors.append(f"{prefix}: OA launch_url must use https://zalo.me/<numeric-oa-id>")

    for optional_url in ("official_website", "logo_url"):
        value = item.get(optional_url)
        if value is not None and not is_http_url(value):
            errors.append(f"{prefix}: {optional_url} must be null or an HTTP(S) URL")

    for field in ("regions", "target_users", "capabilities", "aliases"):
        if not isinstance(item.get(field), list) or not item[field]:
            errors.append(f"{prefix}: {field} must be a non-empty list")
        elif not all(isinstance(value, str) and value.strip() for value in item[field]):
            errors.append(f"{prefix}: {field} must contain non-empty strings")

    organization_contexts = item.get("organization_contexts")
    if not isinstance(organization_contexts, list):
        errors.append(f"{prefix}: organization_contexts must be a list")
    else:
        for context in organization_contexts:
            if not isinstance(context, dict):
                errors.append(f"{prefix}: every organization context must be an object")
                continue
            if (
                not isinstance(context.get("organization"), str)
                or not context["organization"].strip()
            ):
                errors.append(f"{prefix}: context.organization must be non-empty")
            site = context.get("site")
            if site is not None and (not isinstance(site, str) or not site.strip()):
                errors.append(f"{prefix}: context.site must be null or non-empty")
            if context.get("relationship") not in ORGANIZATION_RELATIONSHIPS:
                errors.append(f"{prefix}: invalid context.relationship")
            if context.get("access_scope") not in ACCESS_SCOPES:
                errors.append(f"{prefix}: invalid context.access_scope")
            if context.get("verification_status") not in CONTEXT_VERIFICATION_STATUSES:
                errors.append(f"{prefix}: invalid context.verification_status")
            for aliases_field in ("organization_aliases", "site_aliases"):
                aliases = context.get(aliases_field, [])
                if not isinstance(aliases, list) or not all(
                    isinstance(alias, str) and alias.strip() for alias in aliases
                ):
                    errors.append(f"{prefix}: context.{aliases_field} must be strings")

    intents = item.get("intents")
    if not isinstance(intents, list) or not intents:
        errors.append(f"{prefix}: intents must be a non-empty list")
    else:
        for intent in intents:
            if not isinstance(intent, dict):
                errors.append(f"{prefix}: every intent must be an object")
                continue
            if not isinstance(intent.get("intent"), str) or not intent["intent"].strip():
                errors.append(f"{prefix}: intent name must be a non-empty string")
            queries = intent.get("example_queries")
            if not isinstance(queries, list) or not queries:
                errors.append(f"{prefix}: intent.example_queries must be non-empty")
            elif not all(isinstance(query, str) and query.strip() for query in queries):
                errors.append(f"{prefix}: example queries must be non-empty strings")

    evidence_items = item.get("evidence")
    if not isinstance(evidence_items, list) or not evidence_items:
        errors.append(f"{prefix}: evidence must be a non-empty list")
    else:
        for evidence in evidence_items:
            if not isinstance(evidence, dict):
                errors.append(f"{prefix}: every evidence item must be an object")
                continue
            if not is_http_url(evidence.get("url")):
                errors.append(f"{prefix}: evidence.url must be an HTTP(S) URL")
            if not isinstance(evidence.get("publisher"), str) or not evidence["publisher"].strip():
                errors.append(f"{prefix}: evidence.publisher must be non-empty")
            supports = evidence.get("supports")
            if not isinstance(supports, list) or not supports:
                errors.append(f"{prefix}: evidence.supports must be non-empty")
            elif not all(isinstance(claim, str) and claim.strip() for claim in supports):
                errors.append(f"{prefix}: evidence.supports must contain non-empty strings")
            if not isinstance(evidence.get("checked_at"), str):
                errors.append(f"{prefix}: evidence.checked_at must be a date string")

    if item.get("active") is not False:
        errors.append(f"{prefix}: active must remain false in staging")
    if item.get("review_status") != "candidate":
        errors.append(f"{prefix}: review_status must be 'candidate'")
    if item.get("logo_usage") != "reference_only_needs_review":
        errors.append(f"{prefix}: logo_usage must require review")

    verification = item.get("verification")
    if not isinstance(verification, dict):
        errors.append(f"{prefix}: verification must be an object")
    else:
        if not isinstance(verification.get("official_source"), bool):
            errors.append(f"{prefix}: verification.official_source must be boolean")
        if not isinstance(verification.get("link_reachable"), bool):
            errors.append(f"{prefix}: verification.link_reachable must be boolean")
        if verification.get("cross_linked") not in {True, False, None}:
            errors.append(f"{prefix}: verification.cross_linked must be boolean or null")
        if verification.get("confidence") not in CONFIDENCE_LEVELS:
            errors.append(f"{prefix}: invalid verification.confidence")
        if verification.get("oa_badge_status") not in BADGE_STATUSES:
            errors.append(f"{prefix}: invalid verification.oa_badge_status")
        if not isinstance(verification.get("notes"), str):
            errors.append(f"{prefix}: verification.notes must be a string")

    return errors


def main() -> None:
    raw_files = sorted(RAW_DIR.glob("*.json"))
    if not raw_files:
        raise SystemExit(f"No raw JSON files found in {RAW_DIR}")

    services: list[dict[str, Any]] = []
    errors: list[str] = []
    origins: dict[str, str] = {}

    for path in raw_files:
        for raw_record in load_records(path):
            if not isinstance(raw_record, dict):
                errors.append(f"{path.name}: every record must be an object")
                continue
            item = normalize(raw_record)
            errors.extend(validate(item, path))
            candidate_id = item.get("candidate_id")
            if isinstance(candidate_id, str):
                if candidate_id in origins:
                    errors.append(
                        f"duplicate candidate_id {candidate_id!r}: "
                        f"{origins[candidate_id]} and {path.name}"
                    )
                origins[candidate_id] = path.name
            services.append(item)

    if errors:
        raise SystemExit("\n".join(errors))

    services.sort(key=lambda item: (item["category"], item["name"].casefold()))
    payload = {
        "schema_version": "0.1",
        "generated_at": GENERATED_AT,
        "source_scope": "public_first_party_only",
        "services": services,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    category_counts = Counter(item["category"] for item in services)
    channel_counts = Counter(item["channel_type"] for item in services)
    print(f"Wrote {len(services)} candidates to {OUTPUT.relative_to(ROOT)}")
    print(f"Categories: {dict(sorted(category_counts.items()))}")
    print(f"Channels: {dict(sorted(channel_counts.items()))}")
    print(
        "OA badges still unknown: "
        f"{sum(item['verification']['oa_badge_status'] == 'unknown' for item in services)}"
    )


if __name__ == "__main__":
    main()
