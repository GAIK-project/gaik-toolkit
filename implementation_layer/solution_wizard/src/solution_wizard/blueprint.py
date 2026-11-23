"""Pydantic blueprint models -- authoritative schema layer for V1.

These models are the single source of truth. JSON Schema in schemas/ is
exported from them via Blueprint.model_json_schema() and must never be
hand-edited.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

# Size limits. A real blueprint is a few kilobytes with a dozen steps; the limits
# leave ample room and keep validation, cycle checks and generation fast.
MAX_BLUEPRINT_CHARS = 1_000_000
MAX_STEPS = 200
MAX_ITEMS = 500
MAX_EXTERNAL_SERVICES = 20


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
    steps: List[WorkflowStep] = Field(default_factory=list, max_length=MAX_STEPS)


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
# External services (technical_spec.external_services)
# ---------------------------------------------------------------------------
#
# A need that no GAIK component covers (web search, a business register lookup,
# sending e-mail) is met by a third-party API or framework. The scaffolder writes
# each service's package into requirements.txt, which a customer installs with
# ``pip install -r``, and its variable names into .env.example, so both are
# checked here, before any file is written: the package is a plain PyPI
# requirement and every name is one of the service's own.
#
# The patterns are checked with re.fullmatch. They also go into the JSON Schema,
# where ``$`` is the end of the value.

_PIP_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_PIP_SPECIFIER = r"(?:~=|==|!=|<=|>=|<|>)[0-9][0-9A-Za-z.!+*]*"
#: A project name, optional [extras] and optional version specifiers, without
#: spaces: no URL or path, no pip option (-e, --index-url), no environment marker.
PIP_REQUIREMENT_PATTERN = (
    rf"^{_PIP_NAME}(?:\[{_PIP_NAME}(?:,{_PIP_NAME})*\])?"
    rf"(?:{_PIP_SPECIFIER}(?:,{_PIP_SPECIFIER})*)?$"
)
#: Projects the PoC installs for itself: gaik, and what the scaffolder writes beside it
#: in requirements.txt (pydantic, python-dotenv, pyyaml, and reportlab for a PDF
#: report). A service that named one would pin it against the PoC (``gaik<0.5``,
#: ``pydantic==1.0``), and pip would then fail or install a version the PoC cannot
#: run on. Compared as pip compares names (PEP 503).
POC_OWN_PROJECTS = frozenset({"gaik", "pydantic", "python-dotenv", "pyyaml", "reportlab"})
ENV_VAR_PATTERN = r"^[A-Z][A-Z0-9_]*$"
_HTTPS_URL_PATTERN = r"^https://[^\s]+$"
#: One line of text: no line break or other control character.
_ONE_LINE_PATTERN = r"^[^\x00-\x1f\x7f\x85\u2028\u2029]+$"

#: Variables of gaik, the model providers, the wizard's sandbox, the Python process,
#: the network and TLS settings every HTTP client reads, and the installers. A
#: service that named one would have the PoC send that key to a third party (the
#: sandbox holds the provider's key under these names), or route the model calls,
#: provider key included, through a proxy or a certificate the service chose.
#: gaik's own include the provider it picks (LLM_PROVIDER), the addresses it trusts
#: with a key (TTS_ENDPOINT, TYPESAFE_BASE_URL, API_BASE for Docling) and the
#: transcriber's settings (TranscriptionConfig.from_env); a test reads gaik's source
#: and fails on a variable gaik reads that is missing here.
RESERVED_ENV_PREFIXES = (
    "GAIK_",
    "AZURE_",
    "OPENAI_",
    "AITTA_",
    "GOOGLE_",
    "GEMINI_",
    "VERTEX_",
    "ANTHROPIC_",
    "LITELLM_",
    "LOCAL_TRANSCRIBER_",
    "DOCLING_",
    "TYPESAFE_",
    "TRANSCRIPTION_",
    "WHISPER_",
    "GPT4O_",
    "FFMPEG_",
    "WIZARD_",
    "PYTHON",
    "PIP_",
    "UV_",
    "CONDA_",
    "LD_",
    "DYLD_",
)
RESERVED_ENV_NAMES = frozenset(
    {
        "EMBEDDING_MODEL",
        "LLM_PROVIDER",
        "TTS_ENDPOINT",
        "API_BASE",
        "API_TIMEOUT_SECONDS",
        "AUDIO_BITRATE",
        "AUDIO_CHANNELS",
        "AUDIO_SAMPLE_RATE",
        "CHUNK_DURATION_MINUTES",
        "CHUNK_OVERLAP_SECONDS",
        "MAX_429_RETRIES",
        "MAX_RETRIES",
        "MAX_SINGLE_FILE_MB",
        "RESPONSE_FORMAT",
        "RETRY_BASE_DELAY_SECONDS",
        "HOME",
        "PATH",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
    }
)

#: ``data_sent`` of a service that receives nothing, a library that runs locally.
#: Only these words count, in any case and with an optional full stop. Any other
#: wording counts as data sent, also one that starts like them: "None of the
#: documents; the query text goes to Tavily" and "No data beyond the company name"
#: both name something that leaves.
NOTHING_SENT = "none"
_NOTHING_SENT_WORDINGS = frozenset({"none", "nothing", "no data"})


def sends_nothing(data_sent: str) -> bool:
    """True only when ``data_sent`` is "none", "nothing" or "no data" and nothing more."""
    text = " ".join(data_sent.split()).lower()
    return text.removesuffix(".").rstrip() in _NOTHING_SENT_WORDINGS


def project_name(requirement: str) -> str:
    """A plain requirement's project name as pip compares it (PEP 503)."""
    match = re.match(_PIP_NAME, requirement)
    return re.sub(r"[-_.]+", "-", match.group(0) if match else requirement).lower()


def env_name_problem(name: Any) -> str | None:
    """Why ``name`` cannot be an external service's variable, or None when it can."""
    if not isinstance(name, str) or len(name) > 64 or not re.fullmatch(ENV_VAR_PATTERN, name):
        return f"{name!r} must be an UPPER_CASE name (letters, digits, _), at most 64 characters"
    upper = name.upper()
    if upper in RESERVED_ENV_NAMES or upper.startswith(RESERVED_ENV_PREFIXES):
        return (
            f"{name!r} belongs to gaik, the model providers, the sandbox, Python, the "
            "network or the installers; give the service a name of its own, for example "
            "SEARCH_API_KEY"
        )
    return None


class ExternalService(BaseModel):
    """An API or framework outside GAIK that one need of the use case depends on."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        max_length=80,
        description="The service or framework, e.g. 'Tavily web search'.",
        json_schema_extra={"pattern": _ONE_LINE_PATTERN},
    )
    purpose: str = Field(max_length=300, description="The need it meets in this use case.")
    python_package: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "The pip requirement the PoC installs, e.g. 'tavily-python>=0.5'. A plain "
            "PyPI name with optional [extras] and version specifiers, and not one the "
            "PoC installs for itself (gaik, pydantic, python-dotenv, pyyaml, reportlab); "
            "omit it when the service is called with what the PoC already has."
        ),
        json_schema_extra={"pattern": PIP_REQUIREMENT_PATTERN},
    )
    env_vars: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Names of the service's own keys and settings, set in .env.",
        json_schema_extra={
            "items": {"type": "string", "maxLength": 64, "pattern": ENV_VAR_PATTERN}
        },
    )
    docs_url: str | None = Field(
        default=None,
        max_length=300,
        description="The service's documentation (https).",
        json_schema_extra={"pattern": _HTTPS_URL_PATTERN},
    )
    data_sent: str = Field(
        max_length=300,
        description=(
            "What leaves for the third party. For a library that runs locally write "
            f"'{NOTHING_SENT}' and nothing more ('nothing' and 'no data' count the same); "
            "any other wording counts as data sent."
        ),
    )
    user_can_provide: bool = Field(
        description="The user's answer: they can get the account, key and terms for it."
    )
    fallback: str = Field(
        max_length=300,
        description="What the PoC does without the service, as in the sandbox, which has no key.",
    )

    @field_validator("name")
    @classmethod
    def _one_line_name(cls, value: str) -> str:
        if not re.fullmatch(_ONE_LINE_PATTERN, value) or not value.strip():
            raise ValueError("name must be one line of text")
        return value.strip()

    @field_validator("purpose", "data_sent", "fallback")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("python_package")
    @classmethod
    def _plain_requirement(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(PIP_REQUIREMENT_PATTERN, value):
            raise ValueError(
                f"python_package {value!r} must be a plain PyPI requirement such as "
                "'tavily-python>=0.5': a name, optional [extras] and optional version "
                "specifiers, with no spaces; no URL, path, pip option, environment "
                "marker or line break"
            )
        if value is not None and project_name(value) in POC_OWN_PROJECTS:
            raise ValueError(
                f"python_package {value!r} names {project_name(value)}, which the PoC "
                f"installs for itself ({', '.join(sorted(POC_OWN_PROJECTS))}); a service's "
                "package would pin it against the PoC. Name the service's own package, or "
                "omit python_package"
            )
        return value

    @field_validator("env_vars")
    @classmethod
    def _own_names(cls, value: list[str]) -> list[str]:
        problems = [p for p in (env_name_problem(name) for name in value) if p]
        if problems:
            raise ValueError("env_vars: " + "; ".join(problems))
        return list(dict.fromkeys(value))

    @field_validator("docs_url")
    @classmethod
    def _https_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            url = urlsplit(value)
            host = url.hostname
        except ValueError:
            host = None
        if not re.fullmatch(_HTTPS_URL_PATTERN, value) or not host or url.username or url.password:
            raise ValueError(
                f"docs_url {value!r} must be an https address with no user or password"
            )
        return value


_EXTERNAL_SERVICES = TypeAdapter(list[ExternalService])


def check_external_services(value: Any) -> list[ExternalService]:
    """``technical_spec.external_services`` as checked services; ValueError names each problem."""
    if not isinstance(value, list):
        raise ValueError("technical_spec.external_services must be a list")
    if len(value) > MAX_EXTERNAL_SERVICES:
        raise ValueError(
            f"technical_spec.external_services has {len(value)} entries; "
            f"the limit is {MAX_EXTERNAL_SERVICES}"
        )
    try:
        return _EXTERNAL_SERVICES.validate_python(value)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error["loc"])
            message = error["msg"].removeprefix("Value error, ")
            problems.append(f"technical_spec.external_services{where}: {message}")
        raise ValueError("; ".join(problems)) from None


def external_services(blueprint: Blueprint) -> list[ExternalService]:
    """The blueprint's external services, checked again: the spec is a plain dict
    that code may have changed since the blueprint was loaded."""
    spec = blueprint.technical_spec if isinstance(blueprint.technical_spec, dict) else {}
    value = spec.get("external_services")
    return [] if value is None else check_external_services(value)


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
    participants: List[Participant] = Field(default_factory=list, max_length=MAX_ITEMS)
    manual_steps: List[ManualStep] = Field(default_factory=list, max_length=MAX_STEPS)
    external_parties: List[ExternalParty] = Field(default_factory=list, max_length=MAX_ITEMS)
    message_flows: List[MessageFlow] = Field(default_factory=list, max_length=MAX_ITEMS)
    exceptions: List[ExceptionFlow] = Field(default_factory=list, max_length=MAX_ITEMS)
    decision_points: List[DecisionPoint] = Field(default_factory=list, max_length=MAX_ITEMS)


# ---------------------------------------------------------------------------
# Top-level Blueprint
# ---------------------------------------------------------------------------


class Blueprint(BaseModel):
    blueprint_version: str = "1.0"
    metadata: Metadata = Metadata()
    use_case: UseCase
    business_spec: Dict[str, Any] = {}
    # A free-form dict, except external_services, which is checked
    # (_check_external_services) because it reaches requirements.txt and .env.example.
    technical_spec: Dict[str, Any] = Field(
        default={},
        json_schema_extra={
            "properties": {
                "external_services": {
                    "type": "array",
                    "maxItems": MAX_EXTERNAL_SERVICES,
                    "items": ExternalService.model_json_schema(),
                }
            }
        },
    )
    target_output_spec: Dict[str, Any] = {}
    assumptions: List[Assumption] = []
    artifacts: Dict[str, Artifact] = Field(default_factory=dict, max_length=MAX_ITEMS)
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

    @model_validator(mode="before")
    @classmethod
    def _limit_total_size(cls, data: Any) -> Any:
        """Refuse a blueprint whose JSON form is larger than MAX_BLUEPRINT_CHARS."""
        if isinstance(data, dict):
            size = len(json.dumps(data, default=str, ensure_ascii=False))
            if size > MAX_BLUEPRINT_CHARS:
                raise ValueError(
                    f"blueprint is {size} characters as JSON; the limit is {MAX_BLUEPRINT_CHARS}"
                )
        return data

    @field_validator("technical_spec")
    @classmethod
    def _check_external_services(cls, spec: dict[str, Any]) -> dict[str, Any]:
        """Refuse an external service whose package or variable names are not plain."""
        if spec.get("external_services") is None:
            return spec
        services = check_external_services(spec["external_services"])
        return {
            **spec,
            "external_services": [s.model_dump(exclude_none=True) for s in services],
        }

    @classmethod
    def from_file(cls, path: str | Path) -> "Blueprint":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def fingerprint(self) -> Dict[str, str]:
        """Which blueprint an output came from: its id, version and content hash.

        The hash is the SHA-256 of the blueprint's canonical JSON (sorted keys, no
        spaces), leaving out ``visualizations``: generate_bpmn.py writes its mapping
        there, and redrawing a diagram does not change what the blueprint asks for.
        Any other change gives another hash, so a PoC or document whose hash differs
        from the current blueprint's was generated from an earlier version.
        """
        data = self.model_dump(mode="json", exclude={"visualizations"})
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {
            "blueprint_id": self.metadata.blueprint_id or self.use_case.id,
            "blueprint_version": self.blueprint_version,
            "blueprint_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }

    @classmethod
    def export_json_schema(cls, path: str | Path) -> None:
        """Export JSON Schema to file (regenerates schemas/use_case_blueprint.schema.json)."""
        schema = cls.model_json_schema()
        # LF on every platform: the exported file is committed.
        Path(path).write_text(json.dumps(schema, indent=2), encoding="utf-8", newline="\n")
