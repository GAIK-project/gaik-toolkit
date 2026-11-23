from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BlueprintVersionSummary(BaseModel):
    version: int
    note: str
    created_at: datetime


class BlueprintContent(BaseModel):
    """V2 session blueprint. Extra BPMN sync fields are persisted in JSONB."""

    name: str = ""
    description: str = ""
    goal: str = ""
    steps: list[dict] = Field(default_factory=list)
    # Populated by BPMN canvas sync (#34 / #48) — data-object label overrides.
    data_objects: dict[str, str] = Field(default_factory=dict)
    # Exclusive/parallel gateway snapshots from canvas (#48).
    gateways: list[dict] = Field(default_factory=list)
    # Persistent repositories → BPMN dataStoreReference (+ send task) via V1 generator.
    integration_targets: list[str] = Field(default_factory=list)


class TargetOutputSpec(BaseModel):
    """The agreed output fields from the agent's draft blueprint
    (``target_output_spec``). Surfaced so the Specification view can show the
    real field schema instead of mock rows (#141, and what #25 asked for)."""

    schema_name: str = ""
    fields: list[str] = Field(default_factory=list)
    field_types: dict[str, str] = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    field_descriptions: dict[str, str] = Field(default_factory=dict)
    allowed_values: dict[str, list[str]] = Field(default_factory=dict)
    missing_value_policy: str = ""
    validation_rules: list[str] = Field(default_factory=list)


class BusinessContext(BaseModel):
    """Business-facing fields the wizard agent gathers into the V1 draft
    blueprint (``use_case.blueprint.json``) but that the reduced V2 blueprint
    does not carry. Surfaced read-only at Gate 1 so the SME sees the gathered
    business framing (#19 current process, #20 knowledge processes, #21
    expected value) — not just JSON/BPMN internals."""

    current_process: str = ""
    pain_points: list[str] = Field(default_factory=list)
    intended_users: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    expected_value: list[str] = Field(default_factory=list)
    knowledge_processes: list[str] = Field(default_factory=list)
    domain: str = ""


class AssumptionItem(BaseModel):
    """One entry from the draft blueprint's ``assumptions[]`` — a gap the wizard
    filled in because information was missing. Surfaced at Gate 1 so the SME can
    review (and, later, confirm) them instead of scanning chat markdown."""

    id: str = ""
    text: str = ""
    status: str = "unconfirmed"
    impact: str = ""


class ExtractionProposal(BaseModel):
    """The extraction rules written before schema generation (Phase 4) and
    whether the field definitions have been generated from them (#251)."""

    prompt_markdown: str = ""
    schema_generated: bool = False
    schema_code: str = ""


class PendingTurn(BaseModel):
    """A chat turn in progress: what the user sent and when."""

    user_message: str
    started_at: datetime


class SessionDetailResponse(BaseModel):
    """Full session state for UI resume (S1-2 + metadata)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    step: int
    status: str
    gate_statuses: dict[str, str]
    metadata: dict
    output_dir: str
    active_version: int
    versions: list[BlueprintVersionSummary]
    blueprint: BlueprintContent
    business_context: BusinessContext | None = None
    target_output_spec: TargetOutputSpec | None = None
    extraction_proposal: ExtractionProposal | None = None
    assumptions: list[AssumptionItem] = Field(default_factory=list)
    messages: list[dict]
    #: The message the wizard is answering right now, if any. It is not in
    #: ``messages`` yet (an exchange is stored when its reply is whole), so a
    #: page loaded mid-reply shows it from here and joins GET /chat/stream.
    pending_turn: PendingTurn | None = None
    #: Whether an agent process is held for this session right now. It is
    #: released when idle for long, when its place is needed, or when the user
    #: ends it (POST /agent/end); the next message starts it again.
    agent_live: bool = False
    created_at: datetime
    updated_at: datetime
