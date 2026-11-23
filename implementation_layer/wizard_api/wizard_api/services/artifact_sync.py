"""Bring the agent's on-disk artifacts into the session the UI reads (#141).

The wizard agent writes its artifacts into the session's ``output_dir`` —
``use_case.blueprint.json`` at spec generation, ``workflow.bpmn`` and the rest
later. The UI, meanwhile, reads the blueprint from the database
(``blueprint_versions``) and the BPMN is generated on demand from that same V2
blueprint. Nothing carried the former into the latter: the only code that
touched the generated files checked that ``use_case.blueprint.json`` *existed*
so the step could advance, and never read it. So the workspace kept showing the
seed blueprint however far the conversation had progressed — the demo-parity
gap in #141.

This module is that bridge, and it is the single place that knows the artifact
filenames and the V1 → V2 blueprint mapping.

Everything here is best-effort: a missing, half-written or malformed artifact
returns ``None`` rather than raising, because the agent writes these files
while the user is mid-conversation and a chat turn must never fail on one.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from sqlalchemy.orm import Session

from wizard_api.models import WizardSession
from wizard_api.schemas.blueprint import BlueprintContent, ExtractionProposal, TargetOutputSpec
from wizard_api.services import blueprint_service

#: Draft blueprint the agent writes at Phase 3, right before Gate 1.
DRAFT_BLUEPRINT_FILE = "use_case.blueprint.json"
#: BPMN the agent writes at the visual-blueprint phase.
WORKFLOW_BPMN_FILE = "workflow.bpmn"
#: Mermaid workflow diagram written alongside the BPMN.
WORKFLOW_MMD_FILE = "workflow.mmd"

#: The diagram the UI shows, written for the agent next to its own files. The UI
#: renders BPMN generated from the session blueprint, not the agent's
#: workflow.bpmn, so without these the agent explained a different diagram.
UI_VIEW_DIR = "ui_view"
UI_VIEW_BPMN_FILE = f"{UI_VIEW_DIR}/workflow.bpmn"
UI_VIEW_MAPPING_FILE = f"{UI_VIEW_DIR}/bpmn_mapping.json"
UI_VIEW_BLUEPRINT_FILE = f"{UI_VIEW_DIR}/blueprint.json"

#: Session metadata key: digest of the blueprint content last adopted from the
#: agent's draft, so an unchanged draft is not adopted again over a newer user
#: version (see sync_blueprint_from_draft).
ADOPTED_DRAFT_KEY = "agent_draft_digest"

#: The agent's package and the files it writes there as the phases go by.
POC_DIR = "poc"
EXTRACTION_PROMPT_FILE = "prompts/extraction_requirements.md"
OUTPUT_SCHEMA_PY_FILE = "schemas/output_schema.py"
SCHEMA_FILES = ("schemas/output_schema_requirements.json", OUTPUT_SCHEMA_PY_FILE)
PACKAGE_ENTRYPOINT = "run_poc.py"
_MAX_PROPOSAL_TEXT_BYTES = 64 * 1024

#: UI step that each artifact shows the agent has reached: the artifact closes
#: a phase, so the session moves to the phase that follows it (#169). Gate steps
#: are the exception: the BPMN closes the visual-blueprint phase and the next
#: thing is Gate 2 itself. Mirrors the UI's phase list (4 = Gate 1, 5 schema,
#: 6 components, 7 blueprint, 8 BPMN, 9 = Gate 2, 10 PoC).
STEP_GATE_1 = 4
STEP_AFTER_SCHEMA = 6
STEP_AFTER_COMPONENTS = 7
STEP_BPMN = 8
STEP_GATE_2 = 9
STEP_POC = 10

#: V1 workflow step type → V2 UI step type. ``decision`` has no V2 equivalent
#: (gateways live in ``Blueprint.gateways``), so it is shown as an automated
#: step rather than dropped from the flow.
_V1_TO_V2_STEP_TYPE = {
    "user_task": "io",
    "automated_task": "ai",
    "human_review": "human_review",
    "decision": "ai",
}


def v2_step_type(v1_type: str, component: str) -> str:
    """The V2 step type, using the component as the tie-breaker.

    V1's ``automated_task`` covers two different things: a step where a toolkit
    component calls a model, and a step that just moves data — writing the
    result to a spreadsheet, saving a file. Mapping both to ``ai`` labelled
    "Export results to Excel" as an AI step in the workflow the user reviews.

    A component is what does the model call, so an automated step without one is
    plain work, not AI. The same tie-breaker covers a type we do not recognise:
    guessing ``ai`` for an unknown step was the least safe default, since it
    claims the wizard is doing something it may not be.

    A ``decision`` keeps its existing mapping: it is a branch in the workflow
    rather than work, and reclassifying gateways is not what this is about.
    """
    if v1_type == "automated_task" and not component:
        return "io"
    mapped = _V1_TO_V2_STEP_TYPE.get(v1_type)
    if mapped is not None:
        return mapped
    return "ai" if component else "io"


def artifact_path(output_dir: str, filename: str) -> str:
    return os.path.join(output_dir or "", filename)


def _open_artifact(output_dir: str, filename: str, mode: str = "r"):
    """Open a session file, refusing a symlink in its place (OSError).

    The agent writes in the session directory, so a link there could point the
    API's own reads and writes at files outside it.
    """
    flags = os.O_RDONLY if mode == "r" else os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(artifact_path(output_dir, filename), flags | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, mode, encoding="utf-8")


def read_draft_blueprint(output_dir: str) -> dict[str, Any] | None:
    """Parse the agent's draft blueprint, or ``None`` if it is not (yet) there."""
    try:
        with _open_artifact(output_dir, DRAFT_BLUEPRINT_FILE) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _poc_file_mtime(poc: str, relative: str) -> int | None:
    # poc_service also imports this module for the package's blueprint.
    from wizard_api.services import poc_service

    path = os.path.join(poc, relative)
    if not poc_service.regular_file(path, poc):
        return None
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _read_poc_text(poc: str, relative: str) -> str:
    """Read bounded UTF-8 text from a PoC file checked by ``_poc_file_mtime``."""
    path = os.path.join(poc, relative)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as fh:
            data = fh.read(_MAX_PROPOSAL_TEXT_BYTES + 1)
    except OSError:
        return ""
    if len(data) > _MAX_PROPOSAL_TEXT_BYTES:
        return ""
    return data.decode("utf-8", errors="replace").strip()


def read_extraction_proposal(output_dir: str) -> ExtractionProposal | None:
    """The Phase 4 extraction rules and whether their schema has been generated (#251).

    Returns ``None`` when neither ``extraction_requirements.md`` nor any schema
    file has been written yet.
    """
    if not output_dir:
        return None
    poc = artifact_path(output_dir, POC_DIR)
    if os.path.islink(poc):
        return None
    prompt_mtime = _poc_file_mtime(poc, EXTRACTION_PROMPT_FILE)
    prompt_markdown = (
        _read_poc_text(poc, EXTRACTION_PROMPT_FILE) if prompt_mtime is not None else ""
    )
    schema_files = []
    for name in SCHEMA_FILES:
        mtime = _poc_file_mtime(poc, name)
        if mtime is not None and (
            not prompt_markdown or prompt_mtime is None or mtime >= prompt_mtime
        ):
            schema_files.append(name)
    schema_generated = bool(schema_files)
    if not prompt_markdown and not schema_generated:
        return None
    return ExtractionProposal(
        prompt_markdown=prompt_markdown,
        schema_generated=schema_generated,
        schema_code=(
            _read_poc_text(poc, OUTPUT_SCHEMA_PY_FILE)
            if OUTPUT_SCHEMA_PY_FILE in schema_files
            else ""
        ),
    )


def has_draft_blueprint(output_dir: str) -> bool:
    return os.path.exists(artifact_path(output_dir, DRAFT_BLUEPRINT_FILE))


def _has_component(draft: dict[str, Any]) -> bool:
    return any(_str(step.get("component")) for step in _steps_from_draft(draft))


def step_reached(output_dir: str) -> int | None:
    """The furthest UI step the agent's artifacts justify, or ``None`` before Gate 1.

    The session's step used to stop at Gate 1 while the agent went on to write
    the schema, choose components, assemble the blueprint and draw the BPMN:
    the timeline and the workspace tab stayed on step 4 for the rest of the
    conversation (#169). The files the wizard writes say where it is; the
    caller decides how far the gates let the session follow.
    """
    draft = read_draft_blueprint(output_dir)
    if draft is None:
        return STEP_GATE_1 if has_draft_blueprint(output_dir) else None
    step = STEP_GATE_1
    poc = artifact_path(output_dir, POC_DIR)
    if any(os.path.exists(os.path.join(poc, name)) for name in SCHEMA_FILES):
        step = STEP_AFTER_SCHEMA
    if _has_component(draft):
        step = STEP_AFTER_COMPONENTS
    if os.path.exists(artifact_path(output_dir, WORKFLOW_BPMN_FILE)):
        step = STEP_GATE_2
    if os.path.exists(os.path.join(poc, PACKAGE_ENTRYPOINT)):
        step = STEP_POC
    return step


def gate_missing(
    gate_key: str, output_dir: str, *, successful_run: bool, sandbox: bool
) -> str | None:
    """What the agent has still to produce before ``gate_key`` can be approved, or ``None``.

    A gate is a review point: the user approves what the agent has shown. The
    panel let a gate be approved before there was anything behind it — Gate 2
    was approved while the agent was still working, with no components, no
    blueprint and no diagram, and the agent then built the rest on an approval
    that covered nothing (customer test feedback, 17 Oct 2026). The files the
    agent writes say what exists, the same reading ``step_reached`` makes.

    Gate 3 sits after the PoC run (#96): with a sandbox configured it needs a
    run that succeeded; without one, the package itself. Gate 4 has nothing
    file-based to check.
    """
    if gate_key == "gate_1":
        if not has_draft_blueprint(output_dir):
            return "the specification"
        return None
    if gate_key == "gate_2":
        draft = read_draft_blueprint(output_dir)
        missing = []
        if draft is None or not _has_component(draft):
            missing.append("the component selection and the blueprint")
        if not os.path.exists(artifact_path(output_dir, WORKFLOW_BPMN_FILE)):
            missing.append("the workflow diagram")
        return " and ".join(missing) or None
    if gate_key == "gate_3":
        if not os.path.exists(os.path.join(artifact_path(output_dir, POC_DIR), PACKAGE_ENTRYPOINT)):
            return "the PoC package"
        if sandbox and not successful_run:
            return "a successful sandbox run"
        return None
    return None


def write_ui_view(
    output_dir: str, xml: str, mapping: dict[str, Any], v1_blueprint: dict[str, Any]
) -> bool:
    """Write the UI's diagram, its element mapping and the blueprint the mapping
    points into under ``ui_view/``. Best-effort: ``False`` when it could not."""
    if not output_dir:
        return False
    try:
        view_dir = artifact_path(output_dir, UI_VIEW_DIR)
        if os.path.islink(view_dir):
            return False
        os.makedirs(view_dir, exist_ok=True)
        files = {
            UI_VIEW_BPMN_FILE: xml,
            UI_VIEW_MAPPING_FILE: json.dumps(mapping, ensure_ascii=False, indent=2),
            UI_VIEW_BLUEPRINT_FILE: json.dumps(v1_blueprint, ensure_ascii=False, indent=2),
        }
        for name, text in files.items():
            with _open_artifact(output_dir, name, "w") as fh:
                fh.write(text)
    except OSError:
        return False
    return True


def read_workflow_bpmn(output_dir: str) -> str | None:
    """The agent's own BPMN, when it has written one.

    The UI normally renders BPMN generated from the V2 blueprint, so this is
    for comparison and for the phases where the agent's file is the source.
    """
    try:
        with _open_artifact(output_dir, WORKFLOW_BPMN_FILE) as fh:
            xml = fh.read()
    except OSError:
        return None
    return xml if xml.strip() else None


def _str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _steps_from_draft(draft: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = draft.get("workflow")
    raw_steps = workflow.get("steps") if isinstance(workflow, dict) else None
    if not isinstance(raw_steps, list):
        return []

    steps: list[dict[str, Any]] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        step_id = _str(raw.get("id"))
        name = _str(raw.get("name"))
        if not step_id and not name:
            continue
        component = _str(raw.get("component"))
        step: dict[str, Any] = {
            "id": step_id or name,
            "name": name or step_id,
            "type": v2_step_type(_str(raw.get("type")), component),
        }
        if component:
            step["component"] = component
        # Component parameters are what the SME asked to see alongside the
        # component name (SME-4), and the V2 step carries them as `settings`.
        parameters = raw.get("parameters")
        if isinstance(parameters, dict) and parameters:
            step["settings"] = {
                str(key): value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                for key, value in parameters.items()
            }
        steps.append(step)
    return steps


def blueprint_from_draft(draft: dict[str, Any]) -> BlueprintContent | None:
    """Map the agent's V1 draft blueprint onto the V2 blueprint the UI renders.

    Returns ``None`` when the draft carries no workflow yet — an early draft
    with only business framing must not overwrite the blueprint with an empty
    flow (the business framing is surfaced separately at Gate 1).
    """
    steps = _steps_from_draft(draft)
    if not steps:
        return None

    use_case = draft.get("use_case") if isinstance(draft.get("use_case"), dict) else {}
    business = draft.get("business_spec") if isinstance(draft.get("business_spec"), dict) else {}
    technical = draft.get("technical_spec") if isinstance(draft.get("technical_spec"), dict) else {}

    return BlueprintContent(
        name=_str(use_case.get("name")),
        description=_str(use_case.get("description")),
        goal=_str(business.get("poc_goal")),
        steps=steps,
        integration_targets=_str_list(technical.get("integration_targets")),
    )


def target_output_spec_from_draft(draft: dict[str, Any]) -> TargetOutputSpec | None:
    """The agreed output fields (``target_output_spec``) for the Specification
    view, which until now rendered mock fields."""
    raw = draft.get("target_output_spec")
    if not isinstance(raw, dict):
        return None
    fields = _str_list(raw.get("fields"))
    if not fields:
        return None

    def _str_map(value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {str(k): _str(v) for k, v in value.items() if _str(v)}

    def _list_map(value: object) -> dict[str, list[str]]:
        if not isinstance(value, dict):
            return {}
        return {str(k): _str_list(v) for k, v in value.items() if _str_list(v)}

    return TargetOutputSpec(
        schema_name=_str(raw.get("schema_name")),
        fields=fields,
        field_types=_str_map(raw.get("field_types")),
        required_fields=_str_list(raw.get("required_fields")),
        optional_fields=_str_list(raw.get("optional_fields")),
        field_descriptions=_str_map(raw.get("field_descriptions")),
        allowed_values=_list_map(raw.get("allowed_values")),
        missing_value_policy=_str(raw.get("missing_value_policy")),
        validation_rules=_str_list(raw.get("validation_rules")),
    )


def _without_empties(value: Any) -> Any:
    """The value with empty parts left out, so a missing key equals an empty one."""
    if isinstance(value, dict):
        kept = {key: _without_empties(item) for key, item in value.items()}
        return {key: item for key, item in kept.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        items = [item for item in map(_without_empties, value) if item not in (None, "", [], {})]
        # A list of plain values (input types, a step's dependencies) is a set
        # written down in some order; a list of records keeps its order.
        if all(isinstance(item, (str, int, float, bool)) for item in items):
            return sorted(items, key=str)
        return items
    return value.strip() if isinstance(value, str) else value


def content_digest(content: dict[str, Any]) -> str:
    """A digest of blueprint content that does not depend on key order."""
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: What Gate 2 approves, as the parts of the agent's draft that decide what the
#: solution does: its output fields, its steps and components, who takes part,
#: what goes in and comes out, and which external services (third parties) get
#: data. Wording (descriptions, a step's label, the reason a component was
#: chosen, a service's purpose and fallback, the business text, the change log)
#: is left out on purpose: the agent rewrites it freely, and a reworded sentence
#: is not a changed solution.
_SOLUTION_PARTS: dict[str, tuple[str, ...]] = {
    "target_output_spec": (
        "fields",
        "field_types",
        "required_fields",
        "optional_fields",
        "allowed_values",
        "nested",
    ),
    "technical_spec": (
        "input_types",
        "input_formats",
        "output_types",
        "model_provider",
        "human_review_required",
        "external_services",
    ),
    "business_spec": ("reviewers",),
    "business_process": ("participants",),
}
_COMPONENT_LISTS = ("selected_modules", "selected_building_blocks", "custom_components")
_STEP_PARTS = ("id", "type", "component", "parameters", "depends_on")
#: Of an external service, what says which third party gets what: its name, the
#: package and keys the PoC installs and reads, and the data it is sent.
_SERVICE_PARTS = ("name", "python_package", "env_vars", "data_sent")


def _names(entries: object) -> list[str]:
    """The components a list names, without the words written about each."""
    if not isinstance(entries, list):
        return []
    names = []
    for entry in entries:
        if isinstance(entry, dict):
            entry = entry.get("name") or entry.get("id") or entry.get("component")
        if isinstance(entry, str) and entry.strip():
            names.append(entry.strip())
    return names


def solution_digest(draft: dict[str, Any] | None) -> str | None:
    """A digest of what the approved solution does, or None without a draft.

    Compared after a chat turn with the digest kept when the PoC was accepted:
    a difference means the agent changed the solution the gates had approved.
    """
    if not isinstance(draft, dict):
        return None
    picked: dict[str, Any] = {}
    for section, keys in _SOLUTION_PARTS.items():
        value = draft.get(section)
        if isinstance(value, dict):
            picked[section] = {key: value.get(key) for key in keys}
    services = picked.get("technical_spec", {}).get("external_services")
    if isinstance(services, list):
        picked["technical_spec"]["external_services"] = [
            {key: service.get(key) for key in _SERVICE_PARTS}
            if isinstance(service, dict)
            else service
            for service in services
        ]
    components = draft.get("components")
    if isinstance(components, dict):
        picked["components"] = {key: _names(components.get(key)) for key in _COMPONENT_LISTS}
    workflow = draft.get("workflow")
    steps = workflow.get("steps") if isinstance(workflow, dict) else None
    if isinstance(steps, list):
        picked["steps"] = [
            {key: step.get(key) for key in _STEP_PARTS} for step in steps if isinstance(step, dict)
        ]
    # Nor on how the draft was written down: the agent rewrites the draft while
    # it works (the documents of step 12, a normalising pass), and a key that
    # went from missing to empty is not a change to what was approved.
    return content_digest(_without_empties(picked))


def user_changed_blueprint(db: Session, session: WizardSession) -> bool:
    """True when the active blueprint is not the one last adopted from the agent's draft.

    Only the agent's draft is adopted by the sync; any other version since then
    was saved in the workspace (the Blueprint form, the diagram), so the agent's
    use_case.blueprint.json no longer says what the user sees. ``False`` until a
    draft has been adopted, and for sessions adopted before the digest was kept.
    """
    adopted = (session.session_metadata or {}).get(ADOPTED_DRAFT_KEY)
    if not isinstance(adopted, str):
        return False
    active = blueprint_service.get_active_version(db, session)
    return active is not None and content_digest(active.content) != adopted


def _draft_content(draft: dict[str, Any] | None) -> dict[str, Any] | None:
    """The blueprint content a draft maps to, or None when it maps to nothing."""
    if draft is None:
        return None
    mapped = blueprint_from_draft(draft)
    return mapped.model_dump() if mapped is not None else None


def sync_blueprint_from_draft(
    db: Session,
    session: WizardSession,
    draft: dict[str, Any] | None = None,
    *,
    note: str = "Agentin luonnos",
) -> bool:
    """Record the agent's current draft as the session's blueprint.

    The draft is adopted only when the agent has changed it since it was last
    adopted. The user's saves change the database and never the draft, so
    adopting whatever differed from the active version put the agent's older
    draft back over the user's edit at the next chat message. A new version is
    written only when the mapped content also differs from the active one, so a
    conversation does not accumulate an identical version per chat turn.
    Returns ``True`` when a version was added.
    """
    from_file = draft is None
    if from_file:
        draft = read_draft_blueprint(session.output_dir)
    content = _draft_content(draft)
    if content is None:
        return False
    digest = content_digest(content)
    # The common turn, an unchanged draft, takes no lock.
    if (session.session_metadata or {}).get(ADOPTED_DRAFT_KEY) == digest:
        return False

    # Metadata is one JSONB object: read it fresh and hold the row until the
    # commit, so another writer's keys are not lost (#253). What was adopted is
    # read under the same lock: a sync that read it earlier could adopt a draft
    # another sync had just adopted, over a version the user saved in between.
    db.refresh(session, with_for_update=True)
    if from_file:
        # The draft too: one read before the lock could be older than a draft
        # another sync adopted meanwhile, and would be written over it.
        content = _draft_content(read_draft_blueprint(session.output_dir))
        if content is None:
            db.commit()
            return False
        digest = content_digest(content)
    adopted = (session.session_metadata or {}).get(ADOPTED_DRAFT_KEY)
    # A session whose draft was adopted before the digest was kept: a draft the
    # sync has already written as a version is not new, whatever came after it.
    adopted_before = adopted is None and any(
        version.note == note and version.content == content
        for version in blueprint_service.list_versions(db, session.id)
    )
    active = blueprint_service.get_active_version(db, session)
    added = (
        adopted != digest and not adopted_before and (active is None or active.content != content)
    )
    if added:
        blueprint_service.add_version(db, session, note=note, content=content)
    session.session_metadata = {**session.session_metadata, ADOPTED_DRAFT_KEY: digest}
    db.commit()
    db.refresh(session)
    return added
