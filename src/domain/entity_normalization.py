"""Data-driven canonicalisation for structured entity filters.

This is deliberately separate from LLM intent extraction: the model interprets
natural language, while this module makes equivalent catalog identifiers match
reliably after extraction.  Adding a city or organisation is a data change.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_marks).split())


@cache
def _aliases(namespace: str) -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / "data" / "registry" / "entity-aliases.json"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    namespaces = document.get("namespaces")
    if not isinstance(namespaces, dict) or not isinstance(namespaces.get(namespace), dict):
        raise ValueError(f"unknown entity alias namespace: {namespace}")

    aliases: dict[str, str] = {}
    for canonical, values in namespaces[namespace].items():
        if not isinstance(canonical, str) or not isinstance(values, list):
            raise ValueError("entity aliases must map canonical strings to string lists")
        normalized_canonical = normalize_text(canonical)
        for value in [canonical, *values]:
            if not isinstance(value, str) or not (normalized_value := normalize_text(value)):
                raise ValueError("entity alias values must be non-empty strings")
            previous = aliases.setdefault(normalized_value, normalized_canonical)
            if previous != normalized_canonical:
                raise ValueError(f"ambiguous {namespace} alias: {value}")
    return aliases


def normalize_entity(value: str, namespace: str) -> str:
    """Canonicalise one structured entity value using the editable catalog."""

    normalized = normalize_text(value)
    return _aliases(namespace).get(normalized, normalized)


def normalize_entity_text(value: str, namespace: str) -> str:
    """Canonicalise aliases appearing inside a multi-value catalog field."""

    normalized = normalize_text(value)
    for alias, canonical in sorted(_aliases(namespace).items(), key=lambda item: -len(item[0])):
        normalized = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", canonical, normalized)
    return normalized
