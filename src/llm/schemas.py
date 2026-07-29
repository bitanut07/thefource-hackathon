from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from domain.urls import is_canonical_zalo_oa_url

ServiceCategoryValue = Literal[
    "food",
    "education",
    "shopping",
    "finance",
    "utilities",
    "health",
    "government",
    "other",
]
ClarificationField = Literal["service", "location", "time", "target_user", "organization"]
ResponseMode = Literal["text", "voice", "auto"]


class StructuredQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(
        min_length=1,
        max_length=80,
        description="Ý định ngắn gọn của nhu cầu, hoặc 'unknown' khi không xác định được.",
    )
    category: ServiceCategoryValue | None = Field(
        default=None,
        description="Danh mục dịch vụ Zalo phù hợp nhất; null nếu không suy ra được.",
    )
    service: str | None = Field(
        default=None,
        max_length=160,
        description="Tên thương hiệu hoặc loại dịch vụ người dùng nêu rõ; không tự đề xuất.",
    )
    location: str | None = Field(default=None, max_length=160, description="Địa điểm nêu rõ.")
    time: str | None = Field(default=None, max_length=80, description="Thời điểm nêu rõ.")
    target_user: str | None = Field(
        default=None, max_length=120, description="Nhóm người dùng nêu rõ."
    )
    organization: str | None = Field(
        default=None, max_length=120, description="Tổ chức/công ty nêu rõ."
    )
    needs_clarification: bool = Field(
        default=False,
        description="Chỉ true khi thiếu một trường làm tìm kiếm không hữu ích.",
    )
    clarification_field: ClarificationField | None = Field(
        default=None,
        description="Trường duy nhất cần hỏi thêm khi needs_clarification là true.",
    )
    out_of_scope: bool = Field(
        default=False,
        description="True khi yêu cầu hệ thống thực hiện giao dịch/hành động thay người dùng.",
    )

    response_mode: ResponseMode = "auto"

    @model_validator(mode="after")
    def validate_control_flags(self) -> Self:
        if self.out_of_scope and self.needs_clarification:
            raise ValueError("out_of_scope and needs_clarification cannot both be true")
        if self.needs_clarification != (self.clarification_field is not None):
            raise ValueError(
                "clarification_field must be set exactly when needs_clarification is true"
            )
        return self


class ServiceChoice(BaseModel):
    """Public service card returned by the API without internal ranking data."""

    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    name: str
    service_type: str
    launch_url: HttpUrl
    region: str | None = None
    organization: str | None = None
    reason: str

    @model_validator(mode="after")
    def validate_channel_launch_url(self) -> Self:
        if self.service_type == "oa" and not is_canonical_zalo_oa_url(str(self.launch_url)):
            raise ValueError("OA launch_url must use canonical https://zalo.me/<numeric-oa-id>")
        return self


class ServiceCandidate(ServiceChoice):
    """Internal ranked registry candidate; never serialized directly to clients."""

    score: float = Field(ge=0, le=1)

    def to_public_choice(self) -> ServiceChoice:
        return ServiceChoice.model_validate(
            self.model_dump(exclude={"score"}),
        )


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    choices: list[ServiceChoice] = Field(default_factory=list, max_length=5)
    clarification_question: str | None = None
    handoff_to_human: bool = False
    response_mode: ResponseMode = "auto"
