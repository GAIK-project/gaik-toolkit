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
#: ``Participant.kind`` in solution_wizard's blueprint: a person's role or a system.
LaneKind = Literal["human_role", "system"]

MAX_OPERATIONS = 50
#: The largest request body the operations route reads: 50 operations fit with room.
MAX_REQUEST_BYTES = 64 * 1024
MAX_NAME_CHARS = 200
MAX_DESCRIPTION_CHARS = 2000
MAX_CONDITION_CHARS = 200
#: A decision has 2 to 5 branches.
MIN_BRANCHES = 2
MAX_BRANCHES = 5


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


class AddLane(_Operation):
    """A new lane (``business_process.participants`` entry) that no step is in yet."""

    op: Literal["add_lane"]
    name: str = Field(max_length=MAX_NAME_CHARS)
    kind: LaneKind = "human_role"


class RenameLane(_Operation):
    op: Literal["rename_lane"]
    lane_id: str
    name: str = Field(max_length=MAX_NAME_CHARS)


class RemoveLane(_Operation):
    """Refused (``lane_in_use``) while a step or a manual step is in the lane."""

    op: Literal["remove_lane"]
    lane_id: str


class SetStepLane(_Operation):
    """Who does the step: its ``performed_by``. ``None`` puts it back in the lane of its type."""

    op: Literal["set_step_lane"]
    step_id: str
    lane_id: str | None


class Branch(BaseModel):
    """One way out of a decision: its condition and the step it leads to, or ``"end"``."""

    model_config = ConfigDict(extra="forbid")

    condition: str = Field(min_length=1, max_length=MAX_CONDITION_CHARS)
    target: str


class AddDecision(_Operation):
    """A business decision (``business_process.decision_points``) after the step ``after``."""

    op: Literal["add_decision"]
    after: str
    name: str = Field(max_length=MAX_NAME_CHARS)
    branches: list[Branch] = Field(min_length=MIN_BRANCHES, max_length=MAX_BRANCHES)


class UpdateDecision(_Operation):
    """A decision's new name, or its branches replaced; ``None`` keeps what it has."""

    op: Literal["update_decision"]
    decision_id: str
    name: str | None = Field(default=None, max_length=MAX_NAME_CHARS)
    branches: list[Branch] | None = Field(
        default=None, min_length=MIN_BRANCHES, max_length=MAX_BRANCHES
    )


class RemoveDecision(_Operation):
    op: Literal["remove_decision"]
    decision_id: str


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
        | AddLane
        | RenameLane
        | RemoveLane
        | SetStepLane
        | AddDecision
        | UpdateDecision
        | RemoveDecision
    ),
    Field(discriminator="op"),
]


class OperationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version: int
    operations: list[Operation] = Field(min_length=1, max_length=MAX_OPERATIONS)


class UndoRequest(BaseModel):
    """``POST /blueprint/undo``: the version the workspace shows when it asks."""

    model_config = ConfigDict(extra="forbid")

    base_version: int


class OperationsResponse(BaseModel):
    """The session after the edit, and what the edit left for the agent to complete."""

    session: SessionDetailResponse
    warnings: list[str]
    needs_attention: list[str]
    bpmn_changed: bool
