"""Catalog review console API.

Every route here can change what end users are shown, so all of them require a
console session and every mutation is audited.  Reads deliberately expose the
fields the public catalog API hides — owner, review status, priority, evidence and
the reasons a row may not be published.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Request, Security, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError
from rq import Queue, Worker

from api.admin_auth import require_admin_session
from domain.catalog_admin import (
    AdminServiceRecord,
    CatalogStats,
    PublishGuardError,
    ReviewAction,
    ReviewEvent,
    ReviewStatus,
    ServiceDraft,
    ServicePatch,
    publish_blockers,
)
from domain.catalog_import import (
    MAX_IMPORT_ROWS,
    ImportFormatError,
    parse_service_spreadsheet,
    template_rows,
)
from domain.models import ServiceType
from domain.postgres_admin import PostgresAdminCatalog
from domain.postgres_registry import CatalogUnavailableError
from domain.search import LaunchUrlPolicy

# Bounds the upload before it is read into memory.
MAX_IMPORT_BYTES = 5 * 1024 * 1024

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Review Console"],
    dependencies=[Security(require_admin_session)],
)

# The console reads the whole catalog to compute publish warnings. That is fine at
# the MVP's scale (tens of services) and would need a SQL-side rewrite well before
# the catalog reaches thousands.
_HEALTH_SCAN_LIMIT = 1_000


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


class EvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str
    publisher: str | None
    checked_at: datetime | None
    verification_status: str
    supports: str | None


class IntentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    example_query: str


class AdminServiceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
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
    region: str | None
    target_user: str | None
    organization: str | None
    last_verified_at: datetime | None
    updated_at: datetime | None
    deleted_at: datetime | None
    aliases: list[str]
    intents: list[IntentView]
    evidence: list[EvidenceView]
    has_embedding: bool
    is_publishable: bool
    publish_blockers: list[str]


class AdminServiceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    offset: int
    limit: int
    items: list[AdminServiceView]


class LabelCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    count: int


class CatalogStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    publishable: int
    missing_embedding: int
    deleted: int
    publishable_with_blockers: int
    by_review_status: list[LabelCount]
    by_category: list[LabelCount]
    by_source_type: list[LabelCount]


class ReviewEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    actor: str
    created_at: datetime
    note: str | None
    changed_fields: list[str]
    previous_review_status: str | None
    new_review_status: str | None


class QueueHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_name: str
    queued_jobs: int
    failed_jobs: int
    registered_workers: int
    oldest_queued_job_seconds: float | None


def _catalog(request: Request) -> PostgresAdminCatalog:
    catalog = getattr(request.app.state, "admin_catalog", None)
    if catalog is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Review console cần SEARCH_BACKEND=postgres và DATABASE_URL; "
                "backend JSON chỉ đọc và không ghi được."
            ),
        )
    return cast(PostgresAdminCatalog, catalog)


def _url_policy(request: Request) -> LaunchUrlPolicy:
    return cast(LaunchUrlPolicy, request.app.state.launch_url_policy)


def _to_view(record: AdminServiceRecord, url_policy: LaunchUrlPolicy) -> AdminServiceView:
    blockers = publish_blockers(record, url_policy)
    return AdminServiceView(
        service_id=record.id,
        name=record.name,
        provider=record.provider,
        service_type=record.service_type,
        category=record.category,
        description=record.description,
        launch_url=record.launch_url,
        owner=record.owner,
        active=record.active,
        review_status=record.review_status,
        service_priority=record.service_priority,
        source_type=record.source_type,
        region=record.region,
        target_user=record.target_user,
        organization=record.organization,
        last_verified_at=record.last_verified_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
        aliases=list(record.aliases),
        intents=[
            IntentView(intent=item.intent, example_query=item.example_query)
            for item in record.intents
        ],
        evidence=[
            EvidenceView(
                source_url=item.source_url,
                publisher=item.publisher,
                checked_at=item.checked_at,
                verification_status=item.verification_status,
                supports=item.supports,
            )
            for item in record.evidence
        ],
        has_embedding=record.has_embedding,
        is_publishable=not blockers,
        publish_blockers=list(blockers),
    )


def _unavailable(exc: CatalogUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc) or "Service Catalog PostgreSQL chưa sẵn sàng.",
    )


def _guard_rejected(exc: PublishGuardError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "PUBLISH_GUARD_BLOCKED",
            "message": "Dịch vụ chưa đủ điều kiện để phục vụ người dùng.",
            "blockers": list(exc.blockers),
        },
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy dịch vụ trong Service Catalog.",
    )


@router.get(
    "/services",
    response_model=AdminServiceListResponse,
    summary="Liệt kê toàn bộ catalog theo trạng thái review",
    description=(
        "Trả cả record chưa publish. Mỗi item kèm `publish_blockers` để reviewer "
        "thấy lý do chưa thể duyệt trước khi bấm nút."
    ),
)
async def list_services(
    request: Request,
    review_status: ReviewStatus | None = None,
    service_type: ServiceType | None = None,
    active: bool | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    deleted: Annotated[
        bool | None,
        Query(
            description=("Bỏ trống: chỉ record chưa xóa. true: chỉ record đã xóa. false: cả hai.")
        ),
    ] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminServiceListResponse:
    try:
        records, total = await _catalog(request).list_services(
            review_status=review_status.value if review_status is not None else None,
            service_type=service_type,
            active=active,
            query=q,
            include_deleted=deleted is False,
            deleted_only=deleted is True,
            offset=offset,
            limit=limit,
        )
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    url_policy = _url_policy(request)
    return AdminServiceListResponse(
        total=total,
        offset=offset,
        limit=limit,
        items=[_to_view(record, url_policy) for record in records],
    )


@router.get(
    "/services/{service_id}",
    response_model=AdminServiceView,
    summary="Xem chi tiết một record catalog kèm evidence",
)
async def get_service(service_id: UUID, request: Request) -> AdminServiceView:
    try:
        record = await _catalog(request).get_service(service_id)
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


@router.post(
    "/services",
    response_model=AdminServiceView,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo dịch vụ mới ở trạng thái chờ duyệt",
    description="Record mới luôn được tạo với `active=false`; duyệt là một hành động riêng.",
)
async def create_service(
    request: Request,
    draft: ServiceDraft,
    actor: Annotated[str, Security(require_admin_session)],
) -> AdminServiceView:
    catalog = _catalog(request)
    try:
        # Two rows sharing a deeplink would make the assistant offer the same
        # destination twice, so a duplicate is refused rather than merged.
        existing = await catalog.find_by_launch_url(draft.launch_url)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"launch_url đã tồn tại trong catalog: {existing.name}.",
            )
        record = await catalog.create_service(draft, actor=actor)
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    return _to_view(record, _url_policy(request))


@router.patch(
    "/services/{service_id}",
    response_model=AdminServiceView,
    summary="Sửa một phần record catalog",
    description=(
        "Chỉ ghi các trường được gửi. Sửa nội dung tìm kiếm sẽ xóa embedding cũ "
        "để tránh xếp hạng theo nghĩa lỗi thời; chạy `make catalog-embed` để tạo lại."
    ),
    responses={409: {"description": "Record đang phục vụ sẽ vi phạm guardrail sau khi sửa."}},
)
async def update_service(
    service_id: UUID,
    patch: ServicePatch,
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
) -> AdminServiceView:
    try:
        record = await _catalog(request).update_service(service_id, patch, actor=actor)
    except PublishGuardError as exc:
        raise _guard_rejected(exc) from exc
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


@router.post(
    "/services/{service_id}/approve",
    response_model=AdminServiceView,
    summary="Duyệt và đưa dịch vụ vào phục vụ",
    description=(
        "Đặt `active=true`, `review_status=approved` và ghi `last_verified_at` là "
        "thời điểm duyệt. Bị từ chối nếu launch URL ngoài allowlist, OA không phải "
        "deeplink số chuẩn, kênh không phải OA/Mini App, hoặc category ngoài enum runtime."
    ),
    responses={409: {"description": "Record chưa đủ điều kiện publish."}},
)
async def approve_service(
    service_id: UUID,
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
    payload: NoteRequest | None = None,
) -> AdminServiceView:
    try:
        record = await _catalog(request).approve_service(
            service_id,
            actor=actor,
            verified_at=datetime.now(UTC),
            note=payload.note if payload is not None else None,
        )
    except PublishGuardError as exc:
        raise _guard_rejected(exc) from exc
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


@router.post(
    "/services/{service_id}/reject",
    response_model=AdminServiceView,
    summary="Từ chối một candidate",
    description="Đặt `review_status=rejected` và rút khỏi phục vụ.",
)
async def reject_service(
    service_id: UUID,
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
    payload: NoteRequest | None = None,
) -> AdminServiceView:
    try:
        record = await _catalog(request).reject_service(
            service_id,
            actor=actor,
            note=payload.note if payload is not None else None,
        )
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


@router.post(
    "/services/{service_id}/deactivate",
    response_model=AdminServiceView,
    summary="Tạm rút dịch vụ khỏi phục vụ",
    description=(
        "Dùng khi link OA chết hoặc dịch vụ tạm dừng. Giữ nguyên `review_status` "
        "để phân biệt tạm dừng vận hành với quyết định review."
    ),
)
async def deactivate_service(
    service_id: UUID,
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
    payload: NoteRequest | None = None,
) -> AdminServiceView:
    try:
        record = await _catalog(request).deactivate_service(
            service_id,
            actor=actor,
            note=payload.note if payload is not None else None,
        )
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


@router.delete(
    "/services/{service_id}",
    response_model=AdminServiceView,
    summary="Xóa dịch vụ (soft delete)",
    description=(
        "Đánh dấu đã xóa và rút khỏi phục vụ trong cùng một câu lệnh. Evidence và "
        "lịch sử review được giữ lại — đó là bằng chứng vì sao dịch vụ từng được "
        "phục vụ. Dùng `POST .../restore` để phục hồi."
    ),
)
async def delete_service(
    service_id: UUID,
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
    payload: NoteRequest | None = None,
) -> AdminServiceView:
    try:
        record = await _catalog(request).delete_service(
            service_id,
            actor=actor,
            note=payload.note if payload is not None else None,
        )
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


@router.post(
    "/services/{service_id}/restore",
    response_model=AdminServiceView,
    summary="Phục hồi dịch vụ đã xóa",
    description="Bỏ dấu đã xóa. Record trở lại trạng thái chưa phục vụ; duyệt là bước riêng.",
)
async def restore_service(
    service_id: UUID,
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
    payload: NoteRequest | None = None,
) -> AdminServiceView:
    try:
        record = await _catalog(request).restore_service(
            service_id,
            actor=actor,
            note=payload.note if payload is not None else None,
        )
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    if record is None:
        raise _not_found()
    return _to_view(record, _url_policy(request))


class BulkApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_ids: list[UUID] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class BulkApproveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    name: str | None
    approved: bool
    blockers: list[str]
    error: str | None


class BulkApproveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: int
    failed: int
    results: list[BulkApproveResult]


@router.post(
    "/services/bulk-approve",
    response_model=BulkApproveResponse,
    summary="Duyệt nhiều dịch vụ một lượt",
    description=(
        "Chạy đúng guardrail publish cho từng record và báo kết quả từng dòng. "
        "Một record không đủ điều kiện chỉ làm chính nó thất bại, không hủy cả lô."
    ),
)
async def bulk_approve(
    request: Request,
    payload: BulkApproveRequest,
    actor: Annotated[str, Security(require_admin_session)],
) -> BulkApproveResponse:
    catalog = _catalog(request)
    verified_at = datetime.now(UTC)
    results: list[BulkApproveResult] = []

    for service_id in dict.fromkeys(payload.service_ids):
        try:
            record = await catalog.approve_service(
                service_id,
                actor=actor,
                verified_at=verified_at,
                note=payload.note,
            )
        except PublishGuardError as exc:
            existing = await catalog.get_service(service_id)
            results.append(
                BulkApproveResult(
                    service_id=service_id,
                    name=existing.name if existing is not None else None,
                    approved=False,
                    blockers=list(exc.blockers),
                    error=None,
                )
            )
            continue
        except CatalogUnavailableError as exc:
            # The catalog being down is not a per-row problem; stop rather than
            # reporting every remaining row as individually broken.
            raise _unavailable(exc) from exc
        if record is None:
            results.append(
                BulkApproveResult(
                    service_id=service_id,
                    name=None,
                    approved=False,
                    blockers=[],
                    error="Không tìm thấy dịch vụ.",
                )
            )
            continue
        results.append(
            BulkApproveResult(
                service_id=service_id,
                name=record.name,
                approved=True,
                blockers=[],
                error=None,
            )
        )

    approved = sum(1 for item in results if item.approved)
    return BulkApproveResponse(
        approved=approved,
        failed=len(results) - approved,
        results=results,
    )


class ImportRowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int
    name: str
    created: bool
    service_id: UUID | None
    error: str | None


class ImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: int
    failed: int
    results: list[ImportRowResult]


@router.post(
    "/services/import",
    response_model=ImportResponse,
    summary="Nhập dịch vụ từ file Excel hoặc CSV",
    description=(
        "Nhận `.xlsx` hoặc `.csv`. Mọi dòng đều được tạo ở trạng thái **chờ duyệt** "
        "và không thể phục vụ người dùng cho tới khi có người bấm duyệt — một file "
        "sai không thể tự đẩy liên kết sai ra ngoài.\n\n"
        "Từng dòng được báo cáo riêng, nên dòng lỗi không làm hủy cả file. Dòng có "
        "`launch_url` đã tồn tại trong catalog bị bỏ qua để tránh trùng."
    ),
    responses={
        400: {"description": "File sai định dạng, thiếu cột bắt buộc hoặc quá lớn."},
    },
)
async def import_services(
    request: Request,
    actor: Annotated[str, Security(require_admin_session)],
    file: Annotated[UploadFile, File(description="File .xlsx hoặc .csv")],
) -> ImportResponse:
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File vượt {MAX_IMPORT_BYTES // (1024 * 1024)} MB.",
        )

    try:
        rows = parse_service_spreadsheet(content, file.filename or "upload")
    except ImportFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    catalog = _catalog(request)
    results: list[ImportRowResult] = []
    for row in rows:
        if row.draft is None:
            results.append(
                ImportRowResult(
                    row_number=row.row_number,
                    name=row.name,
                    created=False,
                    service_id=None,
                    error=row.error or "Dòng không hợp lệ.",
                )
            )
            continue
        try:
            existing = await catalog.find_by_launch_url(row.draft.launch_url)
            if existing is not None:
                results.append(
                    ImportRowResult(
                        row_number=row.row_number,
                        name=row.name,
                        created=False,
                        service_id=existing.id,
                        error=f"launch_url đã tồn tại trong catalog ({existing.name}).",
                    )
                )
                continue
            created = await catalog.create_service(
                row.draft,
                actor=actor,
                note=f"Nhập từ {file.filename or 'file'} dòng {row.row_number}",
                action=ReviewAction.IMPORT,
            )
        except CatalogUnavailableError as exc:
            raise _unavailable(exc) from exc
        results.append(
            ImportRowResult(
                row_number=row.row_number,
                name=created.name,
                created=True,
                service_id=created.id,
                error=None,
            )
        )

    created_count = sum(1 for item in results if item.created)
    return ImportResponse(
        created=created_count,
        failed=len(results) - created_count,
        results=results,
    )


@router.get(
    "/services/import/template",
    summary="Tải file mẫu để nhập dịch vụ",
    description=(
        "CSV UTF-8 gồm dòng tiêu đề và một dòng ví dụ. Mở được bằng Excel; lưu lại "
        "dạng .xlsx cũng nhập được."
    ),
    response_class=StreamingResponse,
)
async def import_template() -> StreamingResponse:
    headers, example = template_rows()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerow(example)
    # The BOM makes Excel read UTF-8 correctly instead of mangling Vietnamese.
    payload = "﻿" + buffer.getvalue()
    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="fone-services-template.csv"',
            "X-Max-Rows": str(MAX_IMPORT_ROWS),
        },
    )


@router.get(
    "/services/{service_id}/events",
    response_model=list[ReviewEventView],
    summary="Lịch sử review của một record",
)
async def list_review_events(
    service_id: UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReviewEventView]:
    catalog = _catalog(request)
    try:
        record = await catalog.get_service(service_id)
        if record is None:
            raise _not_found()
        events: tuple[ReviewEvent, ...] = await catalog.review_events(service_id, limit=limit)
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    return [
        ReviewEventView(
            action=event.action,
            actor=event.actor,
            created_at=event.created_at,
            note=event.note,
            changed_fields=list(event.changed_fields),
            previous_review_status=event.previous_review_status,
            new_review_status=event.new_review_status,
        )
        for event in events
    ]


@router.get(
    "/stats",
    response_model=CatalogStatsResponse,
    summary="Số liệu tổng quan catalog",
    description=(
        "`publishable_with_blockers` là số record đang phục vụ nhưng đã vi phạm "
        "guardrail — khác 0 nghĩa là `/health/ready` sẽ báo 503."
    ),
)
async def catalog_stats(request: Request) -> CatalogStatsResponse:
    catalog = _catalog(request)
    try:
        stats: CatalogStats = await catalog.stats()
        served, _total = await catalog.list_services(active=True, limit=_HEALTH_SCAN_LIMIT)
    except CatalogUnavailableError as exc:
        raise _unavailable(exc) from exc
    url_policy = _url_policy(request)
    return CatalogStatsResponse(
        total=stats.total,
        publishable=stats.publishable,
        missing_embedding=stats.missing_embedding,
        deleted=stats.deleted,
        publishable_with_blockers=sum(
            1 for record in served if publish_blockers(record, url_policy)
        ),
        by_review_status=[
            LabelCount(label=label, count=count) for label, count in stats.by_review_status
        ],
        by_category=[LabelCount(label=label, count=count) for label, count in stats.by_category],
        by_source_type=[
            LabelCount(label=label, count=count) for label, count in stats.by_source_type
        ],
    )


@router.get(
    "/queue-health",
    response_model=QueueHealthResponse,
    summary="Trạng thái queue xử lý tin nhắn OA",
    description=(
        "Đủ để phát hiện backlog hoặc job lỗi tăng; không trả nội dung job.\n\n"
        "`oldest_queued_job_seconds` là tín hiệu chính: job nằm chờ lâu nghĩa là "
        "không có ai tiêu thụ. `registered_workers` chỉ mang tính tham khảo — "
        "worker vẫn nhận job qua BLPOP dù bản ghi đăng ký trong Redis đã hết hạn, "
        "nên giá trị 0 không chứng minh là không có worker nào đang chạy."
    ),
)
async def queue_health(request: Request) -> QueueHealthResponse:
    queue = cast(Queue, request.app.state.queue)
    try:
        queued = queue.count
        failed = queue.failed_job_registry.count
        workers = Worker.count(queue=queue)
        oldest_seconds = _oldest_queued_job_seconds(queue)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis chưa sẵn sàng nên chưa đọc được trạng thái queue.",
        ) from exc
    return QueueHealthResponse(
        queue_name=queue.name,
        queued_jobs=int(queued),
        failed_jobs=int(failed),
        registered_workers=int(workers),
        oldest_queued_job_seconds=oldest_seconds,
    )


def _oldest_queued_job_seconds(queue: Queue) -> float | None:
    """Return how long the head-of-queue job has been waiting, if anything waits.

    This measures the symptom that matters — work not being consumed — instead of
    trusting RQ's worker registration, which can expire while a worker is still
    servicing the queue.
    """

    job_ids = queue.get_job_ids(0, 1)
    if not job_ids:
        return None
    job = queue.fetch_job(job_ids[0])
    enqueued_at = job.enqueued_at if job is not None else None
    if enqueued_at is None:
        return None
    if enqueued_at.tzinfo is None:
        enqueued_at = enqueued_at.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - enqueued_at).total_seconds())
