"""Review console tests.

The catalog itself is faked so these run without PostgreSQL or Redis.  What they
pin down is the part that decides what end users see: who may call the console and
which rows it refuses to publish.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from api.admin_auth import MIN_ADMIN_PASSWORD_LENGTH
from config import Settings
from domain.catalog_admin import (
    AdminServiceRecord,
    CatalogStats,
    PublishGuardError,
    ReviewAction,
    ReviewEvent,
    ReviewStatus,
    ServiceDraft,
    ServiceEvidence,
    ServicePatch,
    publish_blockers,
)
from domain.models import ServiceCategory, ServiceIntent, ServiceType
from domain.search import LaunchUrlPolicy

ADMIN_PASSWORD = "review-console-secret"
CANONICAL_OA_URL = "https://zalo.me/3359099682314876895"
ALLOWED_HOSTS = "zalo.me"


def _record(
    *,
    service_id: UUID | None = None,
    name: str = "Edupia",
    service_type: ServiceType = ServiceType.OA,
    category: str = ServiceCategory.EDUCATION.value,
    launch_url: str = CANONICAL_OA_URL,
    active: bool = False,
    review_status: str = ReviewStatus.CANDIDATE.value,
) -> AdminServiceRecord:
    return AdminServiceRecord(
        id=service_id or uuid4(),
        name=name,
        provider="Educa Corporation",
        service_type=service_type,
        category=category,
        description="Nền tảng học tiếng Anh trực tuyến.",
        launch_url=launch_url,
        owner="service-catalog-review",
        active=active,
        review_status=review_status,
        service_priority=90,
        source_type="research",
        has_embedding=False,
        region="online",
        aliases=("EDUPIA",),
        intents=(ServiceIntent(intent="hoc_tieng_anh", example_query="học tiếng Anh cho con"),),
        evidence=(
            ServiceEvidence(
                source_url="https://edupia.vn",
                publisher="Edupia",
                checked_at=datetime(2026, 7, 23, tzinfo=UTC),
                verification_status="official_source",
            ),
        ),
    )


class FakeAdminCatalog:
    """In-memory stand-in that keeps the real publish guardrail."""

    def __init__(self, records: list[AdminServiceRecord], url_policy: LaunchUrlPolicy) -> None:
        self.records = {record.id: record for record in records}
        self.url_policy = url_policy
        self.events: list[tuple[UUID, ReviewAction, str, str | None]] = []

    async def list_services(
        self,
        *,
        review_status: str | None = None,
        service_type: ServiceType | None = None,
        active: bool | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[tuple[AdminServiceRecord, ...], int]:
        matches = [
            record
            for record in self.records.values()
            if (review_status is None or record.review_status == review_status)
            and (service_type is None or record.service_type == service_type)
            and (active is None or record.active == active)
            and (query is None or query.casefold() in record.name.casefold())
        ]
        matches.sort(key=lambda record: (record.active, record.name, str(record.id)))
        return tuple(matches[offset : offset + limit]), len(matches)

    async def get_service(self, service_id: UUID) -> AdminServiceRecord | None:
        return self.records.get(service_id)

    async def create_service(
        self,
        draft: ServiceDraft,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord:
        created = _record(
            name=draft.name,
            service_type=draft.service_type,
            category=draft.category.value,
            launch_url=draft.launch_url,
            active=False,
            review_status=ReviewStatus.CANDIDATE.value,
        )
        self.records[created.id] = created
        self.events.append((created.id, ReviewAction.CREATE, actor, note))
        return created

    async def update_service(
        self,
        service_id: UUID,
        patch: ServicePatch,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        current = self.records.get(service_id)
        if current is None:
            return None
        changes: dict[str, Any] = patch.model_dump(exclude_unset=True)
        if "category" in changes:
            changes["category"] = patch.category.value if patch.category is not None else None
        changes.pop("intents", None)
        changes.pop("aliases", None)
        merged = replace(current, **changes)
        if merged.active:
            blockers = publish_blockers(merged, self.url_policy)
            if blockers:
                raise PublishGuardError(blockers)
        self.records[service_id] = merged
        self.events.append((service_id, ReviewAction.UPDATE, actor, note))
        return merged

    async def approve_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        verified_at: datetime,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        current = self.records.get(service_id)
        if current is None:
            return None
        blockers = publish_blockers(current, self.url_policy)
        if blockers:
            raise PublishGuardError(blockers)
        approved = replace(
            current,
            active=True,
            review_status=ReviewStatus.APPROVED.value,
            last_verified_at=verified_at,
        )
        self.records[service_id] = approved
        self.events.append((service_id, ReviewAction.APPROVE, actor, note))
        return approved

    async def reject_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        return self._withdraw(
            service_id, ReviewStatus.REJECTED.value, ReviewAction.REJECT, actor, note
        )

    async def deactivate_service(
        self,
        service_id: UUID,
        *,
        actor: str,
        note: str | None = None,
    ) -> AdminServiceRecord | None:
        current = self.records.get(service_id)
        if current is None:
            return None
        return self._withdraw(
            service_id, current.review_status, ReviewAction.DEACTIVATE, actor, note
        )

    def _withdraw(
        self,
        service_id: UUID,
        review_status: str,
        action: ReviewAction,
        actor: str,
        note: str | None,
    ) -> AdminServiceRecord | None:
        current = self.records.get(service_id)
        if current is None:
            return None
        updated = replace(current, active=False, review_status=review_status)
        self.records[service_id] = updated
        self.events.append((service_id, action, actor, note))
        return updated

    async def stats(self) -> CatalogStats:
        records = list(self.records.values())
        return CatalogStats(
            total=len(records),
            publishable=sum(1 for record in records if record.active),
            missing_embedding=sum(1 for record in records if not record.has_embedding),
            by_review_status=(("candidate", len(records)),),
            by_category=(("education", len(records)),),
            by_source_type=(("research", len(records)),),
        )

    async def review_events(self, service_id: UUID, *, limit: int = 50) -> tuple[ReviewEvent, ...]:
        return tuple(
            ReviewEvent(
                action=action.value,
                actor=actor,
                created_at=datetime(2026, 7, 29, tzinfo=UTC),
                note=note,
            )
            for recorded_id, action, actor, note in self.events
            if recorded_id == service_id
        )[:limit]


class FakeRedis:
    """Minimal Redis surface used by the session store."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    @classmethod
    def from_url(cls, _url: str, **_options: object) -> "FakeRedis":
        return cls()

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value.encode()
        return True

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    def incr(self, key: str) -> int:
        current = int(self.values.get(key, b"0")) + 1
        self.values[key] = str(current).encode()
        return current

    def expire(self, key: str, seconds: int) -> bool:
        return True


def _create_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    records: list[AdminServiceRecord] | None = None,
    admin_password: str | None = ADMIN_PASSWORD,
) -> tuple[FastAPI, FakeAdminCatalog]:
    monkeypatch.setattr(main, "build_navigator", lambda _settings, **_kwargs: object())
    monkeypatch.setattr(main, "Redis", FakeRedis)
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key=SecretStr("test-only"),
        navigator_api_key=SecretStr("test-navigator-key"),
        admin_password=SecretStr(admin_password) if admin_password is not None else None,
        allowed_launch_hosts=ALLOWED_HOSTS,
        rag_data_path=tmp_path / "rag.sqlite3",
    )
    app = main.create_app(settings)
    catalog = FakeAdminCatalog(
        records if records is not None else [_record()],
        app.state.launch_url_policy,
    )
    app.state.admin_catalog = catalog
    return app, catalog


def _login(client: TestClient, password: str = ADMIN_PASSWORD) -> dict[str, str]:
    response = client.post("/api/v1/admin/session", json={"password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_console_rejects_missing_wrong_and_navigator_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _catalog = _create_app(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.get("/api/v1/admin/services").status_code == 401
    # The read-only machine key must not unlock catalog writes.
    assert (
        client.get(
            "/api/v1/admin/services",
            headers={"X-API-Key": "test-navigator-key"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/admin/services",
            headers={"Authorization": "Bearer not-a-real-session"},
        ).status_code
        == 401
    )
    assert (
        client.post("/api/v1/admin/session", json={"password": "wrong-password"}).status_code == 401
    )


def test_session_lifecycle_revokes_the_token_on_logout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _catalog = _create_app(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = _login(client)

    assert client.get("/api/v1/admin/services", headers=headers).status_code == 200
    assert client.delete("/api/v1/admin/session", headers=headers).status_code == 204
    assert client.get("/api/v1/admin/services", headers=headers).status_code == 401


def test_repeated_failed_logins_are_throttled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _catalog = _create_app(monkeypatch, tmp_path)
    client = TestClient(app)
    attempts = app.state.settings.admin_login_max_attempts

    for _ in range(attempts):
        assert client.post("/api/v1/admin/session", json={"password": "nope"}).status_code == 401

    throttled = client.post("/api/v1/admin/session", json={"password": "nope"})
    assert throttled.status_code == 429
    assert throttled.headers["Retry-After"]
    # A correct password must not bypass the throttle either.
    assert (
        client.post("/api/v1/admin/session", json={"password": ADMIN_PASSWORD}).status_code == 429
    )


def test_console_is_unavailable_until_a_long_enough_password_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    short_password = "x" * (MIN_ADMIN_PASSWORD_LENGTH - 1)
    app, _catalog = _create_app(monkeypatch, tmp_path, admin_password=short_password)
    client = TestClient(app)

    assert (
        client.post("/api/v1/admin/session", json={"password": short_password}).status_code == 503
    )
    assert client.get("/api/v1/admin/services").status_code == 503


def test_listing_exposes_review_fields_and_publish_blockers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    blocked = _record(name="Ngoài allowlist", launch_url="https://example.com/promo")
    app, _catalog = _create_app(monkeypatch, tmp_path, records=[_record(), blocked])
    client = TestClient(app)
    headers = _login(client)

    response = client.get("/api/v1/admin/services", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    by_name = {item["name"]: item for item in payload["items"]}
    # Fields the public catalog API deliberately hides are what reviewers need.
    assert by_name["Edupia"]["owner"] == "service-catalog-review"
    assert by_name["Edupia"]["review_status"] == "candidate"
    assert by_name["Edupia"]["evidence"][0]["source_url"] == "https://edupia.vn"
    assert by_name["Edupia"]["is_publishable"] is True
    assert by_name["Edupia"]["publish_blockers"] == []
    assert by_name["Ngoài allowlist"]["is_publishable"] is False
    assert by_name["Ngoài allowlist"]["publish_blockers"]


@pytest.mark.parametrize(
    ("launch_url", "service_type", "category"),
    [
        ("https://example.com/promo", ServiceType.OA, ServiceCategory.EDUCATION.value),
        ("https://zalo.me/edupia", ServiceType.OA, ServiceCategory.EDUCATION.value),
        ("https://zalo.me/3359099682314876895/", ServiceType.OA, ServiceCategory.EDUCATION.value),
        (
            "https://zalo.me/3359099682314876895",
            ServiceType.WEBSITE,
            ServiceCategory.EDUCATION.value,
        ),
        ("https://zalo.me/3359099682314876895", ServiceType.OA, "uncategorized"),
    ],
)
def test_approve_refuses_rows_the_runtime_cannot_serve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    launch_url: str,
    service_type: ServiceType,
    category: str,
) -> None:
    record = _record(launch_url=launch_url, service_type=service_type, category=category)
    app, catalog = _create_app(monkeypatch, tmp_path, records=[record])
    client = TestClient(app)
    headers = _login(client)

    response = client.post(f"/api/v1/admin/services/{record.id}/approve", headers=headers)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "PUBLISH_GUARD_BLOCKED"
    assert detail["blockers"]
    assert catalog.records[record.id].active is False


def test_approve_publishes_a_clean_row_and_stamps_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = _record()
    app, catalog = _create_app(monkeypatch, tmp_path, records=[record])
    client = TestClient(app)
    headers = _login(client)

    response = client.post(
        f"/api/v1/admin/services/{record.id}/approve",
        headers=headers,
        json={"note": "đã đối chiếu website chính chủ"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"] is True
    assert payload["review_status"] == "approved"
    assert payload["last_verified_at"] is not None
    assert catalog.events[-1][1:] == (
        ReviewAction.APPROVE,
        "admin",
        "đã đối chiếu website chính chủ",
    )


def test_editing_a_served_row_into_a_bad_url_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    served = _record(active=True, review_status=ReviewStatus.APPROVED.value)
    app, catalog = _create_app(monkeypatch, tmp_path, records=[served])
    client = TestClient(app)
    headers = _login(client)

    response = client.patch(
        f"/api/v1/admin/services/{served.id}",
        headers=headers,
        json={"launch_url": "https://oa.zalo.me/edupia"},
    )

    assert response.status_code == 409
    assert catalog.records[served.id].launch_url == CANONICAL_OA_URL


def test_editing_an_unpublished_row_is_allowed_and_audited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = _record()
    app, catalog = _create_app(monkeypatch, tmp_path, records=[record])
    client = TestClient(app)
    headers = _login(client)

    response = client.patch(
        f"/api/v1/admin/services/{record.id}",
        headers=headers,
        json={"description": "Mô tả đã được reviewer chỉnh lại.", "service_priority": 50},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Mô tả đã được reviewer chỉnh lại."
    assert response.json()["service_priority"] == 50
    assert catalog.events[-1][1] is ReviewAction.UPDATE


def test_patch_rejects_an_empty_body_and_unknown_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = _record()
    app, _catalog = _create_app(monkeypatch, tmp_path, records=[record])
    client = TestClient(app)
    headers = _login(client)

    assert (
        client.patch(f"/api/v1/admin/services/{record.id}", headers=headers, json={}).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/admin/services/{record.id}",
            headers=headers,
            json={"review_status": "approved"},
        ).status_code
        == 422
    )


def test_deactivate_keeps_review_status_while_reject_records_the_decision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    served = _record(active=True, review_status=ReviewStatus.APPROVED.value)
    candidate = _record(name="Ứng viên", active=False)
    app, _catalog = _create_app(monkeypatch, tmp_path, records=[served, candidate])
    client = TestClient(app)
    headers = _login(client)

    deactivated = client.post(
        f"/api/v1/admin/services/{served.id}/deactivate",
        headers=headers,
        json={"note": "link OA không còn hoạt động"},
    )
    rejected = client.post(f"/api/v1/admin/services/{candidate.id}/reject", headers=headers)

    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert deactivated.json()["review_status"] == "approved"
    assert rejected.status_code == 200
    assert rejected.json()["review_status"] == "rejected"


def test_created_services_start_unpublished(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _catalog = _create_app(monkeypatch, tmp_path, records=[])
    client = TestClient(app)
    headers = _login(client)

    response = client.post(
        "/api/v1/admin/services",
        headers=headers,
        json={
            "name": "Dịch vụ mới",
            "provider": "Nhà cung cấp",
            "service_type": "oa",
            "category": "utilities",
            "description": "Mô tả dịch vụ mới.",
            "launch_url": CANONICAL_OA_URL,
        },
    )

    assert response.status_code == 201
    assert response.json()["active"] is False
    assert response.json()["review_status"] == "candidate"


def test_missing_service_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _catalog = _create_app(monkeypatch, tmp_path, records=[])
    client = TestClient(app)
    headers = _login(client)
    unknown = uuid4()

    assert client.get(f"/api/v1/admin/services/{unknown}", headers=headers).status_code == 404
    assert (
        client.post(f"/api/v1/admin/services/{unknown}/approve", headers=headers).status_code == 404
    )


def test_stats_counts_served_rows_that_now_violate_the_guardrail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A row approved before the allowlist tightened is exactly what makes
    # /health/ready fail, so the dashboard has to surface it.
    stale = _record(
        name="Đã publish nhưng sai URL",
        launch_url="https://example.com/promo",
        active=True,
        review_status=ReviewStatus.APPROVED.value,
    )
    healthy = _record(active=True, review_status=ReviewStatus.APPROVED.value)
    app, _catalog = _create_app(monkeypatch, tmp_path, records=[stale, healthy])
    client = TestClient(app)
    headers = _login(client)

    response = client.get("/api/v1/admin/stats", headers=headers)

    assert response.status_code == 200
    assert response.json()["publishable"] == 2
    assert response.json()["publishable_with_blockers"] == 1


def test_console_reports_unavailable_without_a_postgres_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _catalog = _create_app(monkeypatch, tmp_path)
    app.state.admin_catalog = None
    client = TestClient(app)
    headers = _login(client)

    response = client.get("/api/v1/admin/services", headers=headers)

    assert response.status_code == 503
    assert "postgres" in response.json()["detail"].casefold()
