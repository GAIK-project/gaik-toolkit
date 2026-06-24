import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wizard_api.session_state import MAX_STEP, MIN_STEP, validate_gate_statuses, validate_step


class SessionCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    output_dir: str | None = Field(default=None, max_length=1024)
    metadata: dict = Field(default_factory=dict)

    @field_validator("user_id")
    @classmethod
    def user_id_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("user_id must not be blank")
        return value


class SessionUpdate(BaseModel):
    step: int | None = None
    gate_statuses: dict[str, str] | None = None
    metadata: dict | None = None

    @field_validator("step")
    @classmethod
    def step_in_range(cls, value: int | None) -> int | None:
        if value is not None:
            validate_step(value)
        return value

    @field_validator("gate_statuses")
    @classmethod
    def gates_valid(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is not None:
            validate_gate_statuses(value)
        return value


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    step: int = Field(ge=MIN_STEP, le=MAX_STEP)
    gate_statuses: dict[str, str]
    metadata: dict
    output_dir: str
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
