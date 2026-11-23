"""Typed operations on the full blueprint draft.

The user's edits to the BPMN diagram reach the canonical draft as a list of these
operations; ``services/blueprint_ops.apply_operations`` applies them. Each model
is one member of the ``Operation`` union, discriminated by ``op``: a new operation
is a new model here, added to the union, and a handler in the service.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

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
#: ``"loop_to:"`` and a step id.
MAX_OUTCOME_CHARS = 300
#: ``Artifact.label`` in solution_wizard's blueprint.
MAX_LABEL_CHARS = 200
#: The largest blueprint, as the characters of its JSON: ``MAX_BLUEPRINT_CHARS`` in
#: solution_wizard's ``blueprint.py`` (a test keeps them equal), and the web app's.
MAX_BLUEPRINT_CHARS = 1_000_000
#: The largest body ``PUT /blueprint/full`` reads: a blueprint at its limit,
#: with room for JSON escapes (``\uXXXX``, six bytes for one character).
MAX_FULL_REQUEST_BYTES = 6 * MAX_BLUEPRINT_CHARS + 1024
#: The top-level sections of the draft only the server writes; a full save
#: that changes one is refused (``readonly_section``).
READONLY_SECTIONS = (
    "blueprint_version",
    "metadata",
    "visualizations",
    "package",
    "traceability",
    "change_log",
)
#: How a step has a data object: it uses it (``inputs``) or makes it (``outputs``).
DataRole = Literal["input", "output"]


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


class AddReworkPath(_Operation):
    """A rework or rejection path (``business_process.exceptions``) on the step
    ``attached_to``: ``outcome`` is ``"end"`` or ``"loop_to:<step id>"``, back to
    an earlier step or the same one."""

    op: Literal["add_rework_path"]
    attached_to: str
    name: str = Field(max_length=MAX_NAME_CHARS)
    condition: str = Field(default="", max_length=MAX_CONDITION_CHARS)
    outcome: str = Field(max_length=MAX_OUTCOME_CHARS)


class UpdateReworkPath(_Operation):
    """A path's new name, condition or outcome; ``None`` keeps what it has."""

    op: Literal["update_rework_path"]
    exception_id: str
    name: str | None = Field(default=None, max_length=MAX_NAME_CHARS)
    condition: str | None = Field(default=None, max_length=MAX_CONDITION_CHARS)
    outcome: str | None = Field(default=None, max_length=MAX_OUTCOME_CHARS)


class RemoveReworkPath(_Operation):
    op: Literal["remove_rework_path"]
    exception_id: str


class RenameDataObject(_Operation):
    """A data object's name in the diagram (``Artifact.label``); empty clears it,
    and the generator names the data object itself again."""

    op: Literal["rename_data_object"]
    artifact_id: str
    label: str = Field(max_length=MAX_LABEL_CHARS)


class LinkData(_Operation):
    """The step uses the data object (``input``) or makes it (``output``)."""

    op: Literal["link_data"]
    artifact_id: str
    step_id: str
    role: DataRole


class UnlinkData(_Operation):
    """The step no longer uses or makes the data object. The only step that
    makes a data object another step uses is refused (``still_used``)."""

    op: Literal["unlink_data"]
    artifact_id: str
    step_id: str
    role: DataRole


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
        | AddReworkPath
        | UpdateReworkPath
        | RemoveReworkPath
        | RenameDataObject
        | LinkData
        | UnlinkData
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


class FullBlueprintRequest(BaseModel):
    """``PUT /blueprint/full``: the edited draft, on the version and the draft
    (``draft_digest`` of ``GET /blueprint/full``) the workspace shows."""

    model_config = ConfigDict(extra="forbid")

    base_version: int
    #: The agent changes parts of the draft without a new version (the output
    #: fields, the models, the change log...): only the digest says the file
    #: is still the one the edit started from.
    base_digest: str = Field(max_length=128)
    draft: dict[str, Any]


class FullBlueprintResponse(BaseModel):
    """``GET /blueprint/full``: the draft, its version and the sections the server owns."""

    version: int
    draft: dict[str, Any]
    readonly_sections: list[str]
    #: ``artifact_sync.content_digest`` of ``draft``: a save sends it back as
    #: ``base_digest``.
    draft_digest: str


class OperationsResponse(BaseModel):
    """The session after the edit, and what the edit left for the agent to complete."""

    session: SessionDetailResponse
    warnings: list[str]
    needs_attention: list[str]
    bpmn_changed: bool
