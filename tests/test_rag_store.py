from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from domain.rag_store import RagDocument, SqliteRagStore


def _document(
    document_id: str,
    name: str,
    content: str,
    **overrides: object,
) -> RagDocument:
    values: dict[str, object] = {
        "document_id": document_id,
        "name": name,
        "content": content,
        "source_path": "fixture.json",
        "source_type": "public_first_party_catalog",
        "active": False,
        "launchable": False,
        "review_status": "candidate",
        "verification_status": "candidate_high",
    }
    values.update(overrides)
    return RagDocument(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("prefer_fts", [True, False])
def test_search_is_accent_insensitive_and_has_a_portable_fallback(prefer_fts: bool) -> None:
    with SqliteRagStore(":memory:", prefer_fts=prefer_fts) as store:
        store.replace_documents(
            [
                _document(
                    "catalog:phuc-long",
                    "Phúc Long Rewards",
                    "Quán nước, trà và cà phê trên Zalo Mini App.",
                ),
                _document(
                    "catalog:health",
                    "Bệnh viện Thành phố",
                    "Khám sức khỏe.",
                ),
            ]
        )

        first = store.search('phuc long" OR *')
        second = store.search('phuc long" OR *')

    assert [item.document.document_id for item in first] == ["catalog:phuc-long"]
    assert first == second
    if not prefer_fts:
        assert store.fts_enabled is False


def test_reopening_a_non_fts_database_populates_the_new_fts_index(tmp_path: Path) -> None:
    database_path = tmp_path / "rag.sqlite3"
    with SqliteRagStore(database_path, prefer_fts=False) as store:
        store.replace_documents(
            [
                _document(
                    "catalog:ba-sao",
                    "Ba Sao",
                    "Đồ ăn cho nhân viên VNG.",
                )
            ]
        )

    with SqliteRagStore(database_path, prefer_fts=True) as reopened:
        results = reopened.search("Ba Sao")

        assert reopened.fts_enabled is True
        assert [item.document.document_id for item in results] == ["catalog:ba-sao"]


@pytest.mark.parametrize("prefer_fts", [True, False])
def test_category_filter_is_applied_before_candidate_limit(
    prefer_fts: bool,
) -> None:
    unrelated = [
        _document(
            f"catalog:health-{index:03d}",
            f"VNG health {index:03d}",
            "VNG employee service",
            category="healthcare",
        )
        for index in range(220)
    ]
    requested = _document(
        "catalog:food",
        "VNG food",
        "VNG employee service",
        category="shopping_delivery",
    )

    with SqliteRagStore(":memory:", prefer_fts=prefer_fts) as store:
        store.replace_documents([*unrelated, requested])
        results = store.search(
            "VNG employee service",
            limit=1,
            category="shopping_delivery",
        )

    assert [item.document.document_id for item in results] == ["catalog:food"]


def test_unverified_or_user_reported_documents_cannot_be_launchable() -> None:
    unsafe = _document(
        "pending:ba-sao",
        "Ba Sao",
        "Dịch vụ đồ ăn được người dùng báo cáo.",
        source_type="user_reported",
        active=True,
        launchable=True,
        launch_url="https://example.com",
        verification_status="needs_official_url",
    )

    with SqliteRagStore(":memory:") as store:
        with pytest.raises(ValueError, match="knowledge-only|verification status"):
            store.replace_documents([unsafe])


def test_launchable_documents_require_positive_status_and_allowed_https_host() -> None:
    typo_status = _document(
        "catalog:typo",
        "Typo status",
        "Record không được phép launch.",
        active=True,
        launchable=True,
        launch_url="https://example.com/service",
        review_status="approvd",
        verification_status="verified_high",
    )
    wrong_host = _document(
        "catalog:wrong-host",
        "Wrong host",
        "Record dùng host ngoài allowlist.",
        active=True,
        launchable=True,
        launch_url="https://evil.example/service",
        review_status="approved",
        verification_status="verified_high",
    )
    safe = _document(
        "catalog:safe",
        "Safe",
        "Record đã duyệt.",
        active=True,
        launchable=True,
        launch_url="https://example.com/service",
        review_status="approved",
        verification_status="verified_high",
    )

    with SqliteRagStore(
        ":memory:",
        allowed_launch_hosts=frozenset({"example.com"}),
    ) as store:
        with pytest.raises(ValueError, match="review status"):
            store.replace_documents([typo_status])
        with pytest.raises(ValueError, match="explicitly allowed host"):
            store.replace_documents([wrong_host])

        assert store.replace_documents([safe]) == 1
        assert [
            result.document.document_id
            for result in store.search(
                "Safe",
                launchable_only=True,
            )
        ] == ["catalog:safe"]


def test_build_script_indexes_catalog_and_pending_knowledge(tmp_path: Path) -> None:
    database_path = tmp_path / "rag.sqlite3"
    subprocess.run(
        [
            sys.executable,
            "scripts/build_rag_db.py",
            "--output",
            str(database_path),
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    with SqliteRagStore(database_path) as store:
        assert store.count() >= 38

        ba_sao = store.search("nhân viên VNG mua đồ ăn Ba Sao", limit=3)
        campus = store.search("VNG Campus canteen đồ uống", limit=5)
        highlands = store.search("Highlands quán nước VNG", limit=3)

        ba_sao_document = next(
            item.document
            for item in ba_sao
            if item.document.document_id == "pending:vng-campus-food-ba-sao"
        )
        highlands_document = next(
            item.document
            for item in highlands
            if item.document.document_id == "pending:highlands-rewards-zalo-mini-app"
        )

        assert ba_sao_document.source_type == "user_reported"
        assert ba_sao_document.active is False
        assert ba_sao_document.launchable is False
        assert highlands_document.launchable is False
        assert highlands_document.verification_status == "unverified"
        assert campus[0].document.document_id == "pending:vng-campus-food-amenities"
        assert store.search("Ba Sao", launchable_only=True) == []
