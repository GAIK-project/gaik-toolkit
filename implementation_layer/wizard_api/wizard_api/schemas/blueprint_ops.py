"""Typed operations on the full blueprint draft.

The user's edits to the BPMN diagram reach the canonical draft as a list of these
operations; ``services/blueprint_ops.apply_operations`` applies them. Each model
is one member of the ``Operation`` union, discriminated by ``op``: a new operation
is a new model here, added to the union, and a handler in the service.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from wizard_api.schemas.blueprint import SessionDetailResponse

StepType = Literal["user_task", "automated_task", "human_review"]

MAX_OPERATIONS = 50
#: The largest request body the operations route reads: 50 operations fit with room.
MAX_REQUEST_BYTES = 64 * 1024
MAX_NAME_CHARS = 200
MAX_DESCRIPTION_CHARS = 2000


class _Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenameStep(_Operation):
    op: Literal["rename_step"]
    step_id: str
    name: str = Field(max_length=MAX_NAME_CHARS)


class SetStepDescription(_Operation):
    op: Literal["set_step_description"]
    step_id: str
    description: str = Field(max_length=MAX_DESCRIPTION_CHARS)


class AddStep(_Operation):
    op: Literal["add_step"]
    name: str = Field(max_length=MAX_NAME_CHARS)
    type: StepType
    after: str | None = None
    before: str | None = None


class RemoveStep(_Operation):
    op: Literal["remove_step"]
    step_id: str


class MoveStep(_Operation):
    op: Literal["move_step"]
    step_id: str
    after: str | None


class Connect(_Operation):
    op: Literal["connect"]
    source: str
    target: str


class Disconnect(_Operation):
    op: Literal["disconnect"]
    source: str
    target: str


class SetStepType(_Operation):
    op: Literal["set_step_type"]
    step_id: str
    type: StepType


Operation = Annotated[
    (
        RenameStep
        | SetStepDescription
        | AddStep
        | RemoveStep
        | MoveStep
        | Connect
        | Disconnect
        | SetStepType
    ),
    Field(discriminator="op"),
]


class OperationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version: int
    operations: list[Operation] = Field(min_length=1, max_length=MAX_OPERATIONS)


class OperationsResponse(BaseModel):
    """The session after the edit, and what the edit left for the agent to complete."""

    session: SessionDetailResponse
    warnings: list[str]
    needs_attention: list[str]
    bpmn_changed: bool
