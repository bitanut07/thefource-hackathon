from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StructuredQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    category: str | None = None
    service: str | None = None
    location: str | None = None
    time: str | None = None
    target_user: str | None = None
    needs_clarification: bool = False
    clarification_field: str | None = None
    out_of_scope: bool = False


class ServiceCandidate(BaseModel):
    """Ứng viên lấy từ registry; LLM không được tự tạo các trường này."""

    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    name: str
    service_type: str
    launch_url: HttpUrl
    region: str | None = None
    reason: str
    score: float = Field(ge=0, le=1)


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    choices: list[ServiceCandidate] = Field(default_factory=list, max_length=3)
    clarification_question: str | None = None
    handoff_to_human: bool = False
