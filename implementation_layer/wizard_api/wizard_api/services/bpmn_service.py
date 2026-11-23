"""BPMN generation and sync for wizard_api sessions."""

from __future__ import annotations

from typing import Any

from wizard_api.services import ai_marking, artifact_sync

try:
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.bpmn_generator import generate_bpmn
    from solution_wizard.bpmn_sync import sync_v2_blueprint_from_bpmn_xml
    from solution_wizard.v2_adapter import v2_to_v1_dict

    _SOLUTION_WIZARD_AVAILABLE = True
except ImportError:  # pragma: no cover - optional in minimal installs
    _SOLUTION_WIZARD_AVAILABLE = False


class BpmnGenerationError(RuntimeError):
    pass


def solution_wizard_available() -> bool:
    return _SOLUTION_WIZARD_AVAILABLE


def generate_bpmn_xml(
    v2_blueprint: dict[str, Any],
    *,
    session_id: str,
    agent_draft: dict[str, Any] | None = None,
) -> str:
    return generate_bpmn_view(v2_blueprint, session_id=session_id, agent_draft=agent_draft)[0]


def generate_bpmn_view(
    v2_blueprint: dict[str, Any],
    *,
    session_id: str,
    agent_draft: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The BPMN the UI shows, the element → blueprint mapping the generator
    records for it, and the V1 blueprint the mapping's paths point into.

    With the agent's draft (``use_case.blueprint.json``), the roles and process
    come from it, see :func:`with_agent_process`; a draft that does not fit is
    dropped rather than failing the diagram.
    """
    if not _SOLUTION_WIZARD_AVAILABLE:
        raise BpmnGenerationError("solution_wizard package is not installed")
    v1 = v2_to_v1_dict(v2_blueprint, session_id=session_id)
    if agent_draft:
        try:
            return _render(with_agent_process(v1, v2_blueprint, agent_draft))
        except Exception:  # noqa: BLE001 - a draft that does not fit falls back
            pass
    return _render(v1)


def _render(v1: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    blueprint = Blueprint.model_validate(v1)
    # Marked here, so the file the session keeps and the diagram the API serves
    # are the same bytes, and both say a model made the diagram.
    xml = ai_marking.mark_xml(generate_bpmn(blueprint))
    mapping = dict(blueprint.visualizations.get("bpmn_mapping") or {})
    return xml, mapping, v1


def with_agent_process(
    v1: dict[str, Any], v2_blueprint: dict[str, Any], agent_draft: dict[str, Any]
) -> dict[str, Any]:
    """``v1`` with the participants, roles and process of the agent's draft.

    The V2 blueprint keeps the steps but not who does them, so the V2 → V1
    adapter fills in "Business User", "Reviewer" and "GenAI", and the diagram
    showed those lanes instead of the roles the user agreed with the agent. The
    draft's ``business_process`` and ``business_spec`` roles carry them.

    A step's V1 type comes from the draft only while the V2 step still has the
    type the draft maps to: V2 has no "automated step without a component", so
    such a step came back as a user task in the user's lane, while a type the
    user changed in the UI is kept. A step the draft has reads and writes the
    draft's artifacts, so data objects keep the names the agent gave them and the
    case screens ask for the input by that name. Exceptions are kept only when the steps
    they hang off and loop back to are still in the workflow, and an external
    party only while the step it hands in to is, sending only artifacts the
    diagram has.
    """
    out = dict(v1)
    steps = [dict(step) for step in (v1.get("workflow") or {}).get("steps") or []]
    v2_types = {str(s.get("id")): str(s.get("type") or "") for s in v2_blueprint.get("steps") or []}
    draft_steps = {
        str(s.get("id")): s
        for s in (agent_draft.get("workflow") or {}).get("steps") or []
        if isinstance(s, dict)
    }
    draft_artifacts = {
        str(k): v for k, v in (agent_draft.get("artifacts") or {}).items() if isinstance(v, dict)
    }
    used: set[str] = set()
    for step in steps:
        draft = draft_steps.get(str(step.get("id")))
        if draft is None:
            continue
        draft_type = str(draft.get("type") or "")
        component = str(draft.get("component") or "")
        if draft_type and artifact_sync.v2_step_type(draft_type, component) == v2_types.get(
            str(step.get("id"))
        ):
            step["type"] = draft_type
        # The data the step reads and writes, under the draft's names.
        for key in ("inputs", "outputs"):
            if key in draft:
                refs = [a for a in draft.get(key) or [] if a in draft_artifacts]
                step[key] = refs
                used.update(refs)
    out["workflow"] = {**(v1.get("workflow") or {}), "steps": steps}
    if used:
        # Every artifact becomes a data object, so the ones the adapter made up
        # for steps that now use the draft's would hang in the diagram unlinked.
        linked = {a for step in steps for key in ("inputs", "outputs") for a in step.get(key) or []}
        merged = {**(v1.get("artifacts") or {}), **{a: draft_artifacts[a] for a in used}}
        out["artifacts"] = {a: spec for a, spec in merged.items() if a in linked}

    # Without participants the lanes come from the business_spec roles below,
    # as in the agent's own diagram, not from the adapter's stock participants.
    process = agent_draft.get("business_process")
    if not isinstance(process, dict):
        process = {}
    ids = {str(step.get("id")) for step in steps}
    exceptions = [
        e
        for e in process.get("exceptions") or []
        if isinstance(e, dict)
        and str(e.get("attached_to") or "") in ids
        and _loop_target_exists(str(e.get("outcome") or ""), ids)
    ]
    artifacts = set(out.get("artifacts") or {})
    external_parties = [
        {**party, "sends": [a for a in party.get("sends") or [] if a in artifacts]}
        for party in process.get("external_parties") or []
        if isinstance(party, dict) and str(party.get("to_step") or "") in ids
    ]
    out["business_process"] = {
        "participants": process.get("participants") or [],
        "exceptions": exceptions,
        "external_parties": external_parties,
    }

    # What goes in and comes out, e.g. a PDF output adds the report step.
    tech = agent_draft.get("technical_spec")
    if isinstance(tech, dict):
        types = {k: tech[k] for k in ("input_types", "output_types") if tech.get(k)}
        out["technical_spec"] = {**(v1.get("technical_spec") or {}), **types}

    spec = agent_draft.get("business_spec")
    if isinstance(spec, dict):
        roles = {k: spec[k] for k in ("intended_users", "reviewers") if spec.get(k)}
        out["business_spec"] = {**(v1.get("business_spec") or {}), **roles}
    return out


def _loop_target_exists(outcome: str, step_ids: set[str]) -> bool:
    if not outcome.startswith("loop_to:"):
        return True
    return outcome.removeprefix("loop_to:") in step_ids


def sync_blueprint_from_bpmn(
    v2_blueprint: dict[str, Any],
    bpmn_xml: str,
) -> dict[str, Any]:
    if not _SOLUTION_WIZARD_AVAILABLE:
        raise BpmnGenerationError("solution_wizard package is not installed")
    return sync_v2_blueprint_from_bpmn_xml(v2_blueprint, bpmn_xml)
