"""BPMN generation and sync for wizard_api sessions."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


class BpmnGenerationError(RuntimeError):
    pass


def solution_wizard_available() -> bool:
    return _SOLUTION_WIZARD_AVAILABLE


def generate_bpmn_xml(
    v2_blueprint: dict[str, Any],
    *,
    session_id: str,
    agent_draft: dict[str, Any] | None = None,
    include_data_objects: bool = True,
    extra_lane_ids: frozenset[str] = frozenset(),
) -> str:
    return generate_bpmn_view(
        v2_blueprint,
        session_id=session_id,
        agent_draft=agent_draft,
        include_data_objects=include_data_objects,
        extra_lane_ids=extra_lane_ids,
    )[0]


def generate_bpmn_view(
    v2_blueprint: dict[str, Any],
    *,
    session_id: str,
    agent_draft: dict[str, Any] | None = None,
    include_data_objects: bool = True,
    extra_lane_ids: frozenset[str] = frozenset(),
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The BPMN the UI shows, the element → blueprint mapping the generator
    records for it, and the V1 blueprint the mapping's paths point into.

    The agent's draft (``use_case.blueprint.json``) is the canonical blueprint:
    when it is a valid blueprint with steps, the diagram is drawn from it as it
    is, and the mapping's paths point into it. Otherwise the reduced blueprint is
    drawn, with the roles and process of a draft that fits it, see
    :func:`with_agent_process`; a draft that does not fit is dropped rather than
    failing the diagram. Without data objects (``include_data_objects=False``)
    the diagram is drawn compact. ``extra_lane_ids``: the lanes the user
    added (``artifact_sync.user_lanes``), drawn also while empty, last.
    """
    if not _SOLUTION_WIZARD_AVAILABLE:
        raise BpmnGenerationError("solution_wizard package is not installed")
    if agent_draft:
        drawn = _render_draft(agent_draft, include_data_objects, extra_lane_ids)
        if drawn is not None:
            return drawn
    v1 = v2_to_v1_dict(v2_blueprint, session_id=session_id)
    if agent_draft:
        try:
            return _render(
                with_agent_process(v1, v2_blueprint, agent_draft),
                include_data_objects,
                extra_lane_ids,
            )
        except Exception:  # noqa: BLE001 - a draft that does not fit falls back
            pass
    return _render(v1, include_data_objects, extra_lane_ids)


#: The mapping path of each lane the generator derives, and the participant id
#: that names it (``derived_participants``): a step's performed_by may hold it.
_DERIVED_LANE_IDS = {
    "derived:business_spec.intended_users": "users",
    "derived:system": "system",
    "derived:business_spec.reviewers": "reviewers",
}


def _index(path: str, prefix: str) -> int | None:
    if not (path.startswith(prefix + "[") and path.endswith("]")):
        return None
    number = path[len(prefix) + 1 : -1]
    return int(number) if number.isdigit() else None


#: A data object's mapping path: ``artifacts.<artifact id>``.
_ARTIFACTS_PREFIX = "artifacts."


def named_mapping(mapping: dict[str, Any], drawn_from: dict[str, Any]) -> dict[str, Any]:
    """``mapping`` with what the editor needs beside the paths: each lane's
    ``participant_id`` (the id lane operations take, derived lanes included),
    each step's ``performed_by`` ("" when its type decides its lane), each
    business decision's ``decision`` (its id, name, step and branches, which
    the decision dialog edits), and the ``exception`` of each element that
    draws a rework or rejection path (its id, name, step, condition and
    outcome, which the path dialog edits): the path's gateway and end event,
    and the approval gateway of a review step whose "No" is the path's loop.
    Each data object's ``data_object`` is its artifact's id and ``label`` ("" when
    the generator names it), which a rename and the link operations take."""
    process = drawn_from.get("business_process") or {}
    participants = process.get("participants") or []
    decisions = process.get("decision_points") or []
    steps = (drawn_from.get("workflow") or {}).get("steps") or []
    paths = _paths_of(drawn_from)
    artifacts = drawn_from.get("artifacts") or {}
    named: dict[str, Any] = {}
    for element_id, entry in mapping.items():
        entry = dict(entry) if isinstance(entry, dict) else entry
        path = entry.get("blueprint_path", "") if isinstance(entry, dict) else ""
        exception = paths.get(path) if isinstance(entry, dict) else None
        if exception is not None:
            entry["exception"] = exception
        if isinstance(entry, dict) and entry.get("kind") == "lane":
            i = _index(path, "business_process.participants")
            if i is not None and i < len(participants):
                entry["participant_id"] = str(participants[i].get("id") or "")
            elif path in _DERIVED_LANE_IDS:
                entry["participant_id"] = _DERIVED_LANE_IDS[path]
        elif isinstance(entry, dict) and entry.get("kind") == "decision_point":
            i = _index(path, "business_process.decision_points")
            if i is not None and i < len(decisions) and isinstance(decisions[i], dict):
                entry["decision"] = _decision_entry(decisions[i])
        elif isinstance(entry, dict) and entry.get("kind") == "data_object":
            artifact_id = path[len(_ARTIFACTS_PREFIX) :]
            artifact = artifacts.get(artifact_id) if path.startswith(_ARTIFACTS_PREFIX) else None
            if isinstance(artifact, dict):
                entry["data_object"] = {
                    "id": artifact_id,
                    "label": str(artifact.get("label") or ""),
                }
        elif isinstance(entry, dict):
            i = _index(path, "workflow.steps")
            if i is not None and i < len(steps) and isinstance(steps[i], dict):
                entry["performed_by"] = str(steps[i].get("performed_by") or "")
        named[element_id] = entry
    return named


def _exception_entry(exception: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(exception.get(key) or default)
        for key, default in (
            ("id", ""),
            ("name", ""),
            ("attached_to", ""),
            ("condition", ""),
            ("outcome", "end"),
        )
    }


def _paths_of(drawn_from: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each rework or rejection path by the mapping paths of the elements that
    draw it, as the generator records them: ``business_process.exceptions[i]``
    for a path's own gateway and end event, ``business_process.exceptions.<id>``
    for the end event of a rejection on a review step, and
    ``derived:approval_after:<step id>`` for the approval gateway whose "No"
    loops back as the review step's first rework path to a drawn step (the
    generator draws that loop flow without a mapping entry)."""
    process = drawn_from.get("business_process") or {}
    exceptions = [e for e in process.get("exceptions") or [] if isinstance(e, dict)]
    steps = [
        s for s in (drawn_from.get("workflow") or {}).get("steps") or [] if isinstance(s, dict)
    ]
    drawn = {
        str(s.get("id"))
        for s in [*steps, *(process.get("manual_steps") or [])]
        if isinstance(s, dict)
    }
    out: dict[str, dict[str, Any]] = {}
    for i, exception in enumerate(process.get("exceptions") or []):
        if isinstance(exception, dict):
            out[f"business_process.exceptions[{i}]"] = _exception_entry(exception)
    for exception in exceptions:
        out.setdefault(
            f"business_process.exceptions.{exception.get('id', '')}", _exception_entry(exception)
        )
    for step in steps:
        if step.get("type") != "human_review":
            continue
        rework = next(
            (
                e
                for e in exceptions
                if e.get("attached_to") == step.get("id")
                and str(e.get("outcome") or "").startswith("loop_to:")
            ),
            None,
        )
        if rework is not None and str(rework["outcome"]).split(":", 1)[1].strip() in drawn:
            out[f"derived:approval_after:{step.get('id')}"] = _exception_entry(rework)
    return out


def _decision_entry(decision: dict[str, Any]) -> dict[str, Any]:
    branches = decision.get("branches") or []
    return {
        "id": str(decision.get("id") or ""),
        "name": str(decision.get("name") or ""),
        "after": str(decision.get("after") or ""),
        "branches": [
            # The generator draws an empty target as the end, as the operations name it.
            {"condition": str(b.get("condition") or ""), "target": str(b.get("target") or "end")}
            for b in branches
            if isinstance(b, dict)
        ],
    }


def _render(
    v1: dict[str, Any],
    include_data_objects: bool = True,
    extra_lane_ids: frozenset[str] = frozenset(),
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    blueprint = Blueprint.model_validate(v1)
    # Marked here, so the file the session keeps and the diagram the API serves
    # are the same bytes, and both say a model made the diagram.
    xml = ai_marking.mark_xml(
        generate_bpmn(
            blueprint, include_data_objects=include_data_objects, extra_lane_ids=extra_lane_ids
        )
    )
    mapping = dict(blueprint.visualizations.get("bpmn_mapping") or {})
    return xml, mapping, v1


def _render_draft(
    draft: dict[str, Any],
    include_data_objects: bool,
    extra_lane_ids: frozenset[str] = frozenset(),
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """The diagram of the draft itself, or None when it is no blueprint with steps."""
    workflow = draft.get("workflow")
    if not isinstance(workflow, dict) or not workflow.get("steps"):
        return None
    try:
        blueprint = Blueprint.model_validate(draft)
    except Exception:  # noqa: BLE001 - a draft the model refuses falls back
        return None
    # The mapping is the one of this drawing: a stored one may be from before an edit.
    visualizations = dict(blueprint.visualizations or {})
    visualizations.pop("bpmn_mapping", None)
    blueprint.visualizations = visualizations
    xml = ai_marking.mark_xml(
        generate_bpmn(
            blueprint, include_data_objects=include_data_objects, extra_lane_ids=extra_lane_ids
        )
    )
    mapping = dict(blueprint.visualizations.get("bpmn_mapping") or {})
    return xml, mapping, draft


def with_session_layout(
    xml: str, session_metadata: dict[str, Any] | None, *, include_data_objects: bool = True
) -> str:
    """``xml`` with the layout the user gave this drawing mode laid over it.

    The layout is kept per mode in ``session_metadata["bpmn_layout"]``
    (``bpmn_layout``). Without one, or should it not apply, the drawing is
    returned as it is; laid over, the drawing is marked as a model's work again,
    as re-writing the XML drops the mark's comment.
    """
    from wizard_api.services import bpmn_layout

    layout = bpmn_layout.stored_layout(session_metadata, include_data_objects)
    if not layout:
        return xml
    try:
        return ai_marking.mark_xml(bpmn_layout.apply_layout(xml, layout))
    except Exception:  # noqa: BLE001 - the drawing without the layout beats none
        logger.warning("the stored diagram layout could not be applied", exc_info=True)
        return xml


def data_object_labels(draft: dict[str, Any]) -> dict[str, str]:
    """The name the diagram gives each of the draft's artifacts."""
    from types import SimpleNamespace

    from solution_wizard.bpmn_generator import _data_object_label

    artifacts = draft.get("artifacts") if isinstance(draft.get("artifacts"), dict) else {}
    return {
        str(art_id): _data_object_label(
            str(art_id),
            SimpleNamespace(label=spec.get("label") or "", type=spec.get("type") or ""),
        )
        for art_id, spec in artifacts.items()
        if isinstance(spec, dict)
    }


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
