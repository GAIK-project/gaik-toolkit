"""Pydantic blueprint models -- authoritative schema layer for V1.

These models are the single source of truth. JSON Schema in schemas/ is
exported from them via Blueprint.model_json_schema() and must never be
hand-edited.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class KnowledgeProcess(str, Enum):
    CAPTURE = "knowledge_capture"
    ACCESS = "knowledge_access"
    SYNTHESIS = "knowledge_synthesis"


class BlueprintStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    POC = "poc"
    PRODUCTION_READY = "production_ready"


class ArtifactSource(str, Enum):
    USER_UPLOAD = "user_upload"
    GENERATED = "generated"
    EXTERNAL_SYSTEM = "external_system"
    STATIC_RESOURCE = "static_resource"


class AssumptionStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    OVERRIDDEN = "overridden"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Metadata(BaseModel):
    blueprint_id: str = ""
    created_by: str = "solution_configuration_wizard"
    created_at: str = ""
    last_updated_at: str = ""
    status: BlueprintStatus = BlueprintStatus.DRAFT


class UseCase(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    knowledge_processes: List[KnowledgeProcess] = []


class Artifact(BaseModel):
    type: str
    source: ArtifactSource
    # optional has NO default -- must be explicitly set (spec §10.3)
    optional: bool
    final_output: bool = False
    externally_visible: bool = False
    produced_by: Optional[str] = None
    schema_ref: Optional[str] = None
    overwrite: bool = False

    @model_validator(mode="after")
    def _check_source_rules(self) -> "Artifact":
        # produced_by is for GAIK-generated intermediates only: it names the
        # workflow step whose execution creates the artifact. User-upload
        # artifacts are *captured* by a user_task step (the step lists the
        # artifact in its outputs), but they are not *produced* by the GAIK
        # pipeline -- hence produced_by must be absent for user_upload.
        # This means a user_task step can legally list a user_upload artifact
        # in step.outputs without the artifact having a produced_by field;
        # the two sides (step.outputs vs artifact.produced_by) are independent.
        if self.source == ArtifactSource.GENERATED and self.produced_by is None:
            raise ValueError("Artifact with source='generated' requires 'produced_by' to be set.")
        if self.source == ArtifactSource.USER_UPLOAD and self.produced_by is not None:
            raise ValueError("Artifact with source='user_upload' must not have 'produced_by'.")
        return self


class LoopConfig(BaseModel):
    max_iterations: Optional[int] = None
    loop_condition_ref: Optional[str] = None


class WorkflowStep(BaseModel):
    id: str
    name: str
    type: str  # user_task | automated_task | human_review | decision
    component: Optional[str] = None
    inputs: List[str] = []
    outputs: List[str] = []
    parameters: Dict[str, Any] = {}
    depends_on: List[str] = []
    loop: Optional[LoopConfig] = None


class Workflow(BaseModel):
    steps: List[WorkflowStep] = []


class SelectedModule(BaseModel):
    id: str
    name: str
    reason: str = ""


class Components(BaseModel):
    selected_modules: List[SelectedModule] = []
    selected_building_blocks: List[str] = []
    custom_components: List[str] = []


class Assumption(BaseModel):
    id: str
    text: str
    status: AssumptionStatus = AssumptionStatus.UNCONFIRMED
    impact: str = ""
    recorded_by: str = ""
    recorded_at: str = ""


class DataHandling(BaseModel):
    external_model_api_allowed: bool = True
    local_processing_required: bool = False
    stores_input_data: bool = False
    stores_outputs: bool = True
    retention_policy: str = "not_specified"
    contains_personal_data: str = "unknown"
    output_sensitivity: str = "unknown"
    audit_log_required: bool = False


class Governance(BaseModel):
    data_handling: DataHandling = DataHandling()


class Runtime(BaseModel):
    interface: str = "cli"
    entrypoint: str = ""
    env_file: str = ".env.example"


class Package(BaseModel):
    name: str = ""
    output_dir: str = ""
    include_tests: bool = True
    include_evals: bool = True
    include_docs: bool = True


class TraceabilityEntry(BaseModel):
    component: str
    required_by: str


class ChangeLogEntry(BaseModel):
    version: str
    date: str
    change: str
    changed_by: str


# ---------------------------------------------------------------------------
# Business process (optional Level-2 BPMN enrichment, spec §15.2)
# ---------------------------------------------------------------------------
#
# This whole section is OPTIONAL. Every field defaults to empty so existing
# blueprints (and the test suite) validate unchanged. It exists so the BPMN
# view can be a genuine business-process model: business detail lives in the
# JSON (derived from this section + enrichment conventions), never authored
# only into the diagram. The BPMN is generated from here; it is never the
# source of truth (one-directional, linked-by-derivation).


class Participant(BaseModel):
    """A swimlane (human role) or system lane in the BPMN."""

    id: str
    name: str
    kind: str = "human_role"  # human_role | system
    # Step types whose tasks land in this lane when no explicit lane is given
    # (e.g. ["user_task", "human_review"]).
    default_lane_for: List[str] = []


class ManualStep(BaseModel):
    """A human business step the AI pipeline does not model as a workflow step."""

    id: str
    name: str
    performed_by: str = ""  # Participant id
    type: str = "user_task"  # user_task | manual_task
    depends_on: List[str] = []  # step ids (workflow steps or other manual steps)
    consumes: List[str] = []  # artifact ids
    produces: List[str] = []  # artifact ids


class ExternalParty(BaseModel):
    """A black-box pool outside the organisation that hands inputs in."""

    id: str
    name: str
    sends: List[str] = []  # artifact ids handed in via a message flow
    to_step: str = ""  # step id that receives the handoff


class MessageFlow(BaseModel):
    """A cross-pool message (dashed line in BPMN)."""

    # `from`/`to` are element ids (participant id, external party id, step id,
    # or data store id). `from_` is the Python attribute (from is reserved);
    # JSON uses the natural key "from" via the alias.
    from_: str = ""
    to: str = ""
    name: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _accept_from_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "from" in data and "from_" not in data:
            data = dict(data)
            data["from_"] = data.pop("from")
        return data


class ExceptionFlow(BaseModel):
    """An alternative / error path attached to a step."""

    id: str
    name: str
    attached_to: str = ""  # step id the boundary/branch hangs off
    condition: str = ""
    # "end" -> terminate; "loop_to:<step_id>" -> rework loop back to a step.
    outcome: str = "end"


class DecisionBranch(BaseModel):
    condition: str = ""
    target: str = ""  # step id or "end"


class DecisionPoint(BaseModel):
    """A business gateway beyond the implicit approve/reject one."""

    id: str
    name: str
    after: str = ""  # step id this gateway follows
    branches: List[DecisionBranch] = []


class BusinessProcess(BaseModel):
    participants: List[Participant] = []
    manual_steps: List[ManualStep] = []
    external_parties: List[ExternalParty] = []
    message_flows: List[MessageFlow] = []
    exceptions: List[ExceptionFlow] = []
    decision_points: List[DecisionPoint] = []


# ---------------------------------------------------------------------------
# Top-level Blueprint
# ---------------------------------------------------------------------------


class Blueprint(BaseModel):
    blueprint_version: str = "1.0"
    metadata: Metadata = Metadata()
    use_case: UseCase
    business_spec: Dict[str, Any] = {}
    technical_spec: Dict[str, Any] = {}
    target_output_spec: Dict[str, Any] = {}
    assumptions: List[Assumption] = []
    artifacts: Dict[str, Artifact] = {}
    inputs: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    schemas: Dict[str, Any] = {}
    components: Components = Components()
    workflow: Workflow = Workflow()
    business_process: BusinessProcess = BusinessProcess()
    prompts: Dict[str, Any] = {}
    models: Dict[str, Any] = {}
    validation: Dict[str, Any] = {}
    evaluation: Dict[str, Any] = {}
    governance: Governance = Governance()
    runtime: Runtime = Runtime()
    package: Package = Package()
    visualizations: Dict[str, Any] = {}
    traceability: List[TraceabilityEntry] = []
    change_log: List[ChangeLogEntry] = []

    @classmethod
    def from_file(cls, path: str | Path) -> "Blueprint":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def export_json_schema(cls, path: str | Path) -> None:
        """Export JSON Schema to file (regenerates schemas/use_case_blueprint.schema.json)."""
        schema = cls.model_json_schema()
        Path(path).write_text(json.dumps(schema, indent=2), encoding="utf-8")
