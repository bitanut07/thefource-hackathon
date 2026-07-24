from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

ServiceCategoryValue = Literal[
    "healthcare",
    "utilities",
    "education",
    "transport_public",
    "shopping_delivery",
]
ClarificationField = Literal["service", "location", "time", "target_user", "organization"]


class StructuredQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=80)
    category: ServiceCategoryValue | None = None
    service: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    time: str | None = Field(default=None, max_length=80)
    target_user: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=120)
    needs_clarification: bool = False
    clarification_field: ClarificationField | None = None
    out_of_scope: bool = False

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
    choices: list[ServiceChoice] = Field(default_factory=list, max_length=3)
    clarification_question: str | None = None
    handoff_to_human: bool = False
