from collections.abc import Mapping
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from redis.exceptions import RedisError
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus

from llm.schemas import AgentResponse
from skills.navigator import NavigatorSkill
from worker.jobs import process_message

router = APIRouter(prefix="/demo", tags=["local demo"])


class DemoQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text không được chỉ chứa khoảng trắng")
        return stripped


class QueuedJobResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: AgentResponse | None = None
    error: str | None = None


def _navigator(request: Request) -> NavigatorSkill:
    return cast(NavigatorSkill, request.app.state.navigator)


def _queue(request: Request) -> Queue:
    return cast(Queue, request.app.state.queue)


@router.post("/query", response_model=AgentResponse)
async def query_directly(payload: DemoQueryRequest, request: Request) -> AgentResponse:
    """Run a deterministic text query locally without requiring Zalo OA."""
    return await _navigator(request).process_text(payload.text)


@router.post(
    "/queue",
    response_model=QueuedJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_query(payload: DemoQueryRequest, request: Request) -> QueuedJobResponse:
    """Exercise the Redis/RQ path used by the future Zalo webhook."""
    try:
        job = _queue(request).enqueue(
            process_message,
            {"text": payload.text},
            job_timeout=60,
            result_ttl=600,
            failure_ttl=600,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể kết nối hàng đợi Redis.",
        ) from exc
    return QueuedJobResponse(job_id=job.id, status="queued")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, request: Request) -> JobStatusResponse:
    """Return the current state and validated result of a local demo job."""
    try:
        job = Job.fetch(job_id, connection=_queue(request).connection)
    except NoSuchJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy job.",
        ) from exc
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể kết nối hàng đợi Redis.",
        ) from exc

    try:
        job_status = job.get_status(refresh=True)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể đọc trạng thái job từ Redis.",
        ) from exc

    result: AgentResponse | None = None
    error: str | None = None

    if job_status == JobStatus.FINISHED:
        try:
            raw_result = cast(object, job.return_value())
            if isinstance(raw_result, Mapping):
                result = AgentResponse.model_validate(raw_result)
            else:
                error = "Worker trả kết quả không hợp lệ."
        except RedisError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Không thể đọc kết quả job từ Redis.",
            ) from exc
        except ValidationError:
            error = "Worker trả kết quả không hợp lệ."
    elif job_status == JobStatus.FAILED:
        error = "Job xử lý thất bại; xem worker log để biết chi tiết."

    return JobStatusResponse(
        job_id=job.id,
        status=job_status.value,
        result=result,
        error=error,
    )
