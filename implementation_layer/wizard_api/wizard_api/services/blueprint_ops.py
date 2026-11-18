"""Apply typed operations to the full blueprint draft, repairing references.

Pure: works on a deep copy of a dict and touches no database, file or request.
All operations of a list apply, or none: the first refused one raises
``OperationError`` and the caller's draft is left as it was.

The result is checked with the shared validator. An edit is refused when the
result is not a valid ``Blueprint``, or when it adds an error of a refusing rule
(``REFUSING_RULES``); errors already in the draft do not count. New errors of any
other rule are returned in ``needs_attention`` for the agent to complete.

A new operation is a model in ``schemas/blueprint_ops.py`` and a handler here,
registered in ``_HANDLERS``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from wizard_api.schemas.blueprint_ops import (
    AddDecision,
    AddLane,
    AddReworkPath,
    AddStep,
    Branch,
    Connect,
    Disconnect,
    LinkData,
    MoveStep,
    RemoveDecision,
    RemoveLane,
    RemoveReworkPath,
    RemoveStep,
    RenameDataObject,
    RenameLane,
    RenameStep,
    SetStepDescription,
    SetStepLane,
    SetStepType,
    UnlinkData,
    UpdateDecision,
    UpdateReworkPath,
)

try:
    from solution_wizard import validator
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.bpmn_generator import DERIVED_PARTICIPANT_IDS, derived_participants

    _SOLUTION_WIZARD_AVAILABLE = True
except ImportError:  # pragma: no cover - optional in minimal installs
    _SOLUTION_WIZARD_AVAILABLE = False

#: Validator rules whose new errors refuse an edit: unique step ids, undeclared
#: artifact, produced_by consistency, cycle, unknown performed_by.
REFUSING_RULES = frozenset({1, 2, 7, 8, 16})
_CYCLE_RULE = 8
_HUMAN_TYPES = frozenset({"user_task", "human_review"})
_TYPE_WORDS = {
    "user_task": "user task",
    "automated_task": "automated task",
    "human_review": "human review",
}


def solution_wizard_available() -> bool:
    return _SOLUTION_WIZARD_AVAILABLE


class OperationError(Exception):
    """An operation the draft cannot take. ``code`` is machine-readable:
    ``not_found``, ``last_step``, ``cycle``, ``lane_in_use``, ``unknown_step``,
    ``already_linked``, ``second_producer``, ``still_used``, ``only_producer`` or
    ``invalid``."""

    def __init__(
        self, code: str, message: str, field: str | None = None, index: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        #: The position of the refused operation in the list, when one is to blame.
        self.index = index


@dataclass
class OpsResult:
    blueprint: dict
    summaries: list[str]
    warnings: list[str]
    needs_attention: list[str]
    bpmn_changed: bool
    #: Lane ids ``add_lane`` added and ``remove_lane`` removed, in order.
    lanes_added: list[str] = field(default_factory=list)
    lanes_removed: list[str] = field(default_factory=list)


@dataclass
class _Context:
    blueprint: dict
    summaries: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Steps an operation made automated or added as automated; checked for a
    #: component once all operations have run.
    component_checks: list[str] = field(default_factory=list)
    lanes_added: list[str] = field(default_factory=list)
    lanes_removed: list[str] = field(default_factory=list)

    @property
    def steps(self) -> list[dict]:
        workflow = self.blueprint.setdefault("workflow", {})
        return workflow.setdefault("steps", [])

    @property
    def process(self) -> dict:
        return self.blueprint.setdefault("business_process", {})

    def step(self, step_id: str | None, field_name: str) -> dict:
        for step in self.steps:
            if step.get("id") == step_id:
                return step
        raise OperationError("not_found", f'There is no step "{step_id}"', field_name)

    def index(self, step_id: str) -> int:
        return next(i for i, s in enumerate(self.steps) if s.get("id") == step_id)

    def successors(self, step_id: str) -> list[dict]:
        return [s for s in self.steps if step_id in s.get("depends_on", [])]


# ---------------------------------------------------------------- public helpers


def _slug(name: str) -> str:
    """``name`` as lower-case ASCII letters, digits and ``_``; empty when nothing is left.

    Accented letters lose their marks first (NFKD), so "Käsittele lasku"
    gives ``kasittele_lasku``, not ``k_sittele_lasku``.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")


def new_step_id(name: str, existing: set[str]) -> str:
    """A lower-case slug of ``name``, numbered ``_2``, ``_3``... when it is taken.

    The rule of steps, lanes, decisions and rework paths alike (``_slug``).
    """
    base = _slug(name) or "step"
    candidate, number = base, 1
    while candidate in existing:
        number += 1
        candidate = f"{base}_{number}"
    return candidate


_STEP_DIGEST_FIELDS = {
    "id": None,
    "name": "",
    "type": "",
    "component": None,
    "inputs": [],
    "outputs": [],
    "depends_on": [],
    "description": "",
    "performed_by": "",
}


def bpmn_relevant_digest(blueprint: dict) -> str:
    """SHA-256 of the canonical JSON of the parts of the blueprint the BPMN shows."""
    steps = (blueprint.get("workflow") or {}).get("steps") or []
    technical = blueprint.get("technical_spec") or {}
    business = blueprint.get("business_spec") or {}
    relevant = {
        "steps": [
            {key: step.get(key, default) for key, default in _STEP_DIGEST_FIELDS.items()}
            for step in steps
        ],
        "artifacts": blueprint.get("artifacts") or {},
        "business_process": blueprint.get("business_process") or {},
        "integration_targets": technical.get("integration_targets"),
        "input_types": technical.get("input_types"),
        "output_types": technical.get("output_types"),
        "intended_users": business.get("intended_users"),
        "reviewers": business.get("reviewers"),
        "governance": blueprint.get("governance") or {},
    }
    canonical = json.dumps(
        relevant, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: The V1 type an operation sets for each type of the reduced (V2) blueprint. An
#: ``io`` step becomes a user task, which drops a component: an automated step
#: without one is ``io`` as well, but a step the user made ``io`` is no AI step.
_V2_TO_V1_TYPE = {"io": "user_task", "ai": "automated_task", "human_review": "human_review"}


def _operation(model: type, **fields: Any) -> Any:
    try:
        return model(**fields)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or None
        raise OperationError("invalid", f"{where}: {first['msg']}", where) from None


def _v1_type(step: dict) -> str:
    v2_type = str(step.get("type") or "")
    if v2_type not in _V2_TO_V1_TYPE:
        raise OperationError("invalid", f'Step "{step.get("id")}" has an unknown type', "type")
    return _V2_TO_V1_TYPE[v2_type]


@dataclass(frozen=True)
class SetField:
    """A field of the reduced (V2) blueprint carried into the draft.

    Internal, not an API operation (it is no member of ``Operation``): the old
    saves (the Blueprint form's PATCH, the diagram's ``/bpmn/sync``) send the
    reduced blueprint whole, and what they change outside the steps' order,
    names, types and descriptions reaches the draft as these, applied and
    checked with the operations. ``field`` is one of ``_FIELD_HANDLERS``;
    ``target`` is the step or artifact id where the field is one of theirs.
    """

    field: str
    value: Any
    target: str | None = None


#: What the agent is told of a full save (``ReplaceDraft``).
REPLACED_SUMMARY = "Edited the blueprint as JSON"


@dataclass(frozen=True)
class ReplaceDraft:
    """The whole draft replaced by ``blueprint``: the JSON view's save.

    Internal, not an API operation (``PUT /blueprint/full`` sends the draft
    whole). It is applied and checked as the operations are: the result must
    be a valid blueprint and add no error of a refusing rule, nor a loop.
    """

    blueprint: dict


def operations_from_v2_diff(
    old: dict, new: dict, *, reserved_ids: set[str] | frozenset[str] = frozenset()
) -> list[Any]:
    """The operations that turn ``old``'s steps into ``new``'s, matched by ``id``.

    ``old`` and ``new`` are reduced (V2) blueprints: the draft's reduced view and
    the one a save sends. Only the steps are compared: their ids, order, names,
    types and, where ``new``'s step has one, descriptions. The order is removes,
    then adds (each after the step before it in ``new``; a step added at the
    start comes before the old first step), then moves for the order changes
    left (a step moved to the start is connected to the old first step, so it
    stays in the flow), then renames, descriptions and types.

    A new step's id is the one ``apply_operations`` will give it (``new_step_id``
    of its name), so a later operation can name it; ``reserved_ids`` are ids the
    draft has besides ``old``'s steps (manual steps, steps the view leaves out),
    which a new step does not get. Raises ``OperationError`` for a step the
    operations cannot express (an unknown type, a name over the limit).
    """
    return _v2_diff(old, new, reserved_ids)[0]


def v2_step_ids(
    old: dict, new: dict, *, reserved_ids: set[str] | frozenset[str] = frozenset()
) -> dict[str, str]:
    """Each step id of ``new`` mapped to the id it has in the draft once
    ``operations_from_v2_diff``'s operations are applied."""
    return _v2_diff(old, new, reserved_ids)[1]


def _v2_diff(
    old: dict, new: dict, reserved_ids: set[str] | frozenset[str]
) -> tuple[list[Any], dict[str, str]]:
    old_steps = [s for s in old.get("steps") or [] if isinstance(s, dict)]
    new_steps = [s for s in new.get("steps") or [] if isinstance(s, dict)]
    old_by_id = {str(s.get("id")): s for s in old_steps}
    new_ids = [str(s.get("id")) for s in new_steps]
    kept = set(new_ids)
    if len(kept) != len(new_ids):
        twice = next(sid for sid in new_ids if new_ids.count(sid) > 1)
        raise OperationError("invalid", f'Two steps have the id "{twice}"', "steps")

    ops: list[Any] = []
    order = [sid for sid in old_by_id if sid in kept]
    for sid in old_by_id:
        if sid not in kept:
            ops.append(_operation(RemoveStep, op="remove_step", step_id=sid))

    # The id each step of ``new`` has in the draft once added.
    taken = set(order) | set(reserved_ids)
    real: dict[str, str] = {sid: sid for sid in order}
    for position, step in enumerate(new_steps):
        sid = new_ids[position]
        if sid in old_by_id:
            continue
        after = real[new_ids[position - 1]] if position else None
        # At the start, before the first step: it depends on the new one.
        before = order[0] if after is None and order else None
        name = str(step.get("name") or "")
        add = _operation(
            AddStep, op="add_step", name=name, type=_v1_type(step), after=after, before=before
        )
        new_id = new_step_id(add.name.strip() or "step", taken)
        taken.add(new_id)
        real[sid] = new_id
        order.insert(order.index(after) + 1 if after else 0, new_id)
        ops.append(add)

    target = [real[sid] for sid in new_ids]
    for position, sid in enumerate(target):
        if order[position] == sid:
            continue
        after = target[position - 1] if position else None
        first = order[0]
        ops.append(_operation(MoveStep, op="move_step", step_id=sid, after=after))
        if after is None:
            # A move to the start leaves the step a start that nothing follows.
            ops.append(_operation(Connect, op="connect", source=sid, target=first))
        order.remove(sid)
        order.insert(position, sid)

    renames: list[Any] = []
    descriptions: list[Any] = []
    types: list[Any] = []
    for step in new_steps:
        # A step of ``old`` keeps its id; a new one is matched by the id it gets.
        before = old_by_id.get(str(step.get("id")))
        sid = real[str(step.get("id"))]
        if before is not None:
            name = str(step.get("name") or "")
            if name != str(before.get("name") or ""):
                renames.append(_operation(RenameStep, op="rename_step", step_id=sid, name=name))
            if str(step.get("type") or "") != str(before.get("type") or ""):
                types.append(
                    _operation(SetStepType, op="set_step_type", step_id=sid, type=_v1_type(step))
                )
        description = str(step.get("description") or "")
        was = str(before.get("description") or "") if before is not None else ""
        if "description" in step and description != was:
            descriptions.append(
                _operation(
                    SetStepDescription,
                    op="set_step_description",
                    step_id=sid,
                    description=description,
                )
            )
    return ops + renames + descriptions + types, real


#: Top-level fields of the reduced blueprint and the draft field each comes from
#: (the inverse of ``artifact_sync.blueprint_from_draft``).
_TOP_FIELDS = {
    "name": "use_case_name",
    "description": "use_case_description",
    "goal": "goal",
    "integration_targets": "integration_targets",
}


def _text(value: Any, where: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise OperationError("invalid", f"{where} must be text", where)
    return value.strip()


def _texts(value: Any, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise OperationError("invalid", f"{where} must be a list of texts", where)
    return [v.strip() for v in value if v.strip()]


def _settings(value: Any, where: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
        raise OperationError("invalid", f"{where} must map names to texts", where)
    return {str(k): v for k, v in value.items()}


def field_edits_from_v2_diff(old: dict, new: dict, step_ids: dict[str, str]) -> list[SetField]:
    """The fields outside the steps' order, names, types and descriptions that
    ``new`` gives other values than ``old``, as ``SetField`` edits.

    Those are the inverses of ``artifact_sync.blueprint_from_draft``: the use
    case's name and description, the goal, the integration targets, and each
    step's component and settings (``parameters``). ``step_ids`` maps ``new``'s
    step ids to the draft's (``v2_step_ids``). A missing value and an empty one
    are the same. Raises ``OperationError`` for a value of the wrong kind.
    """
    edits: list[SetField] = []
    for key, field_name in _TOP_FIELDS.items():
        if key == "integration_targets":
            value: Any = _texts(new.get(key), key)
            was: Any = _texts(old.get(key), key)
        else:
            value, was = _text(new.get(key), key), _text(old.get(key), key)
        if value != was:
            edits.append(SetField(field_name, value))
    old_steps = {str(s.get("id")): s for s in old.get("steps") or [] if isinstance(s, dict)}
    for step in new.get("steps") or []:
        if not isinstance(step, dict):
            continue
        before = old_steps.get(str(step.get("id"))) or {}
        sid = step_ids.get(str(step.get("id")), str(step.get("id")))
        where = f"steps[{step.get('id')}]"
        component = _text(step.get("component"), f"{where}.component")
        if component != _text(before.get("component"), f"{where}.component"):
            edits.append(SetField("step_component", component, sid))
        settings = _settings(step.get("settings"), f"{where}.settings")
        if settings != _settings(before.get("settings"), f"{where}.settings"):
            edits.append(SetField("step_settings", settings, sid))
    return edits


def apply_operations(draft: dict, ops: list[Any]) -> OpsResult:
    """Apply every operation to a deep copy of ``draft``, or raise ``OperationError``."""
    ctx = _Context(copy.deepcopy(draft))
    for index, op in enumerate(ops):
        try:
            _HANDLERS[type(op)](ctx, op)
        except OperationError as exc:
            exc.index = index
            raise
    _check_loops(draft, ctx.blueprint)
    needs_attention = _check(draft, ctx.blueprint)
    for step_id in dict.fromkeys(ctx.component_checks):
        step = next((s for s in ctx.steps if s.get("id") == step_id), None)
        if step and step.get("type") == "automated_task" and not step.get("component"):
            needs_attention.insert(0, f"{step_id}: needs a component")
    return OpsResult(
        blueprint=ctx.blueprint,
        summaries=ctx.summaries,
        warnings=ctx.warnings,
        needs_attention=list(dict.fromkeys(needs_attention)),
        bpmn_changed=bpmn_relevant_digest(draft) != bpmn_relevant_digest(ctx.blueprint),
        lanes_added=ctx.lanes_added,
        lanes_removed=ctx.lanes_removed,
    )


# ---------------------------------------------------------------- validation


def _issue_key(issue: Any) -> tuple:
    # Rule 7 names list positions, which shift when a step is added or removed
    # elsewhere; an error already in the draft must still match.
    message = re.sub(r"position \d+", "position", issue.message)
    return issue.rule, issue.step_id, issue.artifact_id, message


def _errors(blueprint: dict) -> dict[tuple, Any]:
    result = validator.validate(Blueprint.model_validate(blueprint))
    return {_issue_key(issue): issue for issue in result.errors}


@dataclass
class _Flow:
    """The flow the diagram draws, between steps (and manual steps).

    It is each step's ``depends_on`` and each business decision's branches. A
    branch back to an earlier step is drawn as a normal flow, which the
    generator's layout cannot rank (rule 8 of the validator reads
    ``depends_on`` only); rework loops are exceptions (``loop_to:``), drawn
    apart, and are not counted.
    """

    #: Step ids, workflow steps first in their order, then the manual steps.
    order: list[str]
    names: dict[str, str]
    successors: dict[str, set[str]]
    #: (after, target) of every decision branch to a step.
    branches: set[tuple[str, str]]

    @classmethod
    def of(cls, blueprint: dict) -> _Flow:
        workflow = blueprint.get("workflow") or {}
        process = blueprint.get("business_process") or {}
        items = [
            i
            for i in [*(workflow.get("steps") or []), *(process.get("manual_steps") or [])]
            if isinstance(i, dict)
        ]
        order = [str(i.get("id")) for i in items]
        flow = cls(
            order, {str(i.get("id")): _label(i) for i in items}, {n: set() for n in order}, set()
        )
        for item in items:
            for dep in item.get("depends_on") or []:
                if dep in flow.successors:
                    flow.successors[dep].add(str(item.get("id")))
        for decision in process.get("decision_points") or []:
            after = decision.get("after") if isinstance(decision, dict) else None
            if after not in flow.successors:
                continue
            for branch in decision.get("branches") or []:
                target = branch.get("target") if isinstance(branch, dict) else None
                if target in flow.successors:
                    flow.successors[after].add(target)
                    flow.branches.add((after, target))
        return flow

    def loops(self) -> list[frozenset[str]]:
        """Each loop as the set of its steps (a strongly connected part)."""

        def reach(start: str) -> set[str]:
            seen: set[str] = set()
            todo = list(self.successors[start])
            while todo:
                node = todo.pop()
                if node not in seen:
                    seen.add(node)
                    todo.extend(self.successors[node])
            return seen

        reached = {n: reach(n) for n in self.order}
        loops: list[frozenset[str]] = []
        for n in self.order:
            if n in reached[n] and not any(n in loop for loop in loops):
                loops.append(frozenset({n} | {m for m in reached[n] if n in reached[m]}))
        return loops

    def leads_back(self, edge: tuple[str, str]) -> bool:
        """Whether a branch goes to its own step or one before it."""
        after, target = edge
        return self.order.index(target) <= self.order.index(after)


def _check_loops(draft: dict, blueprint: dict) -> None:
    """Refuse a loop the operations make, decided by its edges.

    A loop after the edit is the draft's own (an agent may write a branch
    back, and edits beside it are made) when it overlaps a loop of the draft
    and no branch in it is a new one that leads back. So a step added or moved
    within the agent's loop, or a forward decision there, is made; a new
    branch back, inside that loop or not, and a loop where the draft had none
    (a move or a reorder that turns a branch backwards) are refused.
    """
    old, new = _Flow.of(draft), _Flow.of(blueprint)
    before = old.loops()
    for loop in new.loops():
        back = sorted(
            (
                e
                for e in new.branches - old.branches
                if e[0] in loop and e[1] in loop and new.leads_back(e)
            ),
            key=lambda e: new.order.index(e[0]),
        )
        if not back and any(loop & was for was in before):
            continue
        steps = ", ".join(f'"{new.names[sid]}"' for sid in sorted(loop, key=new.order.index))
        if back:
            after, target = back[0]
            why = (
                f'the decision after "{new.names[after]}" would lead back to '
                f'"{new.names[target]}", and a branch cannot lead back to an earlier step'
            )
        else:
            why = "the steps would follow each other in a circle"
        raise OperationError("cycle", f"The edit would make a loop through steps {steps}: {why}")


def _check(draft: dict, blueprint: dict) -> list[str]:
    """Refuse new errors of a refusing rule; return the other new errors."""
    try:
        after = _errors(blueprint)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "blueprint"
        raise OperationError(
            "invalid", f"The result is not a valid blueprint: {where}: {first['msg']}"
        ) from None
    if not after:
        return []
    try:
        before = _errors(draft)
    except ValidationError:
        before = {}
    new = [issue for key, issue in after.items() if key not in before]
    refused = [issue for issue in new if issue.rule in REFUSING_RULES]
    if refused:
        code = "cycle" if any(i.rule == _CYCLE_RULE for i in refused) else "invalid"
        raise OperationError(
            code, "The operations would break the blueprint: " + "; ".join(map(str, refused))
        )
    return [str(issue) for issue in new]


# ---------------------------------------------------------------- handlers


def _name(value: str) -> str:
    name = value.strip()
    if not name:
        raise OperationError("invalid", "A step needs a name", "name")
    return name


def _label(step: dict) -> str:
    return step.get("name") or step.get("id", "")


def _rename_step(ctx: _Context, op: RenameStep) -> None:
    step = ctx.step(op.step_id, "step_id")
    name = _name(op.name)
    ctx.summaries.append(f'Renamed step "{_label(step)}" to "{name}"')
    step["name"] = name


def _set_step_description(ctx: _Context, op: SetStepDescription) -> None:
    step = ctx.step(op.step_id, "step_id")
    step["description"] = op.description
    ctx.summaries.append(f'Changed the description of step "{_label(step)}"')


def _insert(ctx: _Context, step: dict, after: str | None, before: str | None) -> None:
    """Put ``step`` (already in no step's depends_on) after ``after`` and before ``before``.

    With ``before``, ``before`` depends on the step instead of ``after`` (or in
    addition, when it did not depend on ``after``). Without it, a single successor
    of ``after`` moves behind the step; with none the step is the new end, with
    several it starts a new branch. With neither, the step is a new start.
    """
    step["depends_on"] = [after] if after else []
    if before is not None:
        target = ctx.step(before, "before")
        deps = target.setdefault("depends_on", [])
        if after in deps:
            deps[deps.index(after)] = step["id"]
        else:
            deps.append(step["id"])
    elif after is not None:
        successors = ctx.successors(after)
        if len(successors) == 1:
            deps = successors[0]["depends_on"]
            deps[deps.index(after)] = step["id"]
    if after is not None:
        position = ctx.index(after) + 1
    elif before is not None:
        position = ctx.index(before)
    else:
        position = 0  # depends on nothing: a start
    ctx.steps.insert(position, step)


def _add_step(ctx: _Context, op: AddStep) -> None:
    name = _name(op.name)
    after = ctx.step(op.after, "after") if op.after is not None else None
    before = ctx.step(op.before, "before") if op.before is not None else None
    existing = {s.get("id") for s in ctx.steps}
    existing |= {m.get("id") for m in ctx.process.get("manual_steps", [])}
    step = {"id": new_step_id(name, existing), "name": name, "type": op.type}
    step.update(inputs=[], outputs=[], depends_on=[])
    _insert(ctx, step, op.after, op.before)
    if op.type == "automated_task":
        ctx.component_checks.append(step["id"])
    where = "".join(
        [
            f' after "{_label(after)}"' if after else "",
            f' before "{_label(before)}"' if before else "",
        ]
    )
    ctx.summaries.append(f'Added {_TYPE_WORDS[op.type]} "{name}"{where}')


def _bridge(ctx: _Context, step: dict) -> list[dict]:
    """Detach ``step``: its successors depend on its dependencies instead.
    Returns the successors, in step order."""
    step_id = step["id"]
    preds = list(step.get("depends_on", []))
    successors = ctx.successors(step_id)
    for succ in successors:
        deps: list[str] = []
        for dep in succ["depends_on"]:
            for new in preds if dep == step_id else [dep]:
                if new not in deps:
                    deps.append(new)
        succ["depends_on"] = deps
    step["depends_on"] = []
    return successors


def _remove_artifacts(ctx: _Context, step_id: str) -> None:
    artifacts = ctx.blueprint.get("artifacts") or {}
    for art_id in [a for a, art in artifacts.items() if art.get("produced_by") == step_id]:
        del artifacts[art_id]
        consumers = []
        for other in ctx.steps:
            if art_id in other.get("inputs", []):
                other["inputs"] = [a for a in other["inputs"] if a != art_id]
                consumers.append(_label(other))
            if art_id in other.get("outputs", []):
                other["outputs"] = [a for a in other["outputs"] if a != art_id]
        for party in ctx.process.get("external_parties", []):
            party["sends"] = [a for a in party.get("sends", []) if a != art_id]
        for manual in ctx.process.get("manual_steps", []):
            manual["consumes"] = [a for a in manual.get("consumes", []) if a != art_id]
            manual["produces"] = [a for a in manual.get("produces", []) if a != art_id]
        used = f"; it was an input of {', '.join(consumers)}" if consumers else ""
        ctx.warnings.append(f'Removed artifact "{art_id}", which step "{step_id}" produced{used}')


def _remove_step(ctx: _Context, op: RemoveStep) -> None:
    step = ctx.step(op.step_id, "step_id")
    if len(ctx.steps) == 1:
        raise OperationError("last_step", "The workflow needs at least one step", "step_id")
    step_id = step["id"]
    successors = _bridge(ctx, step)
    ctx.steps.pop(ctx.index(step_id))
    _remove_artifacts(ctx, step_id)
    next_id = successors[0]["id"] if successors else "end"

    process = ctx.process
    decisions = [d for d in process.get("decision_points", []) if d.get("after") != step_id]
    for decision in decisions:
        for branch in decision.get("branches", []):
            if branch.get("target") == step_id:
                branch["target"] = next_id
    if "decision_points" in process:
        process["decision_points"] = decisions

    exceptions = [e for e in process.get("exceptions", []) if e.get("attached_to") != step_id]
    for exception in exceptions:
        if exception.get("outcome") == f"loop_to:{step_id}":
            exception["outcome"] = "end"
    if "exceptions" in process:
        process["exceptions"] = exceptions

    gone = {step_id}
    parties = []
    for party in process.get("external_parties", []):
        if party.get("to_step") == step_id:
            if not successors:
                gone.add(party.get("id"))
                continue
            party["to_step"] = next_id
        parties.append(party)
    if "external_parties" in process:
        process["external_parties"] = parties

    for manual in process.get("manual_steps", []):
        manual["depends_on"] = [d for d in manual.get("depends_on", []) if d != step_id]
    if "message_flows" in process:
        process["message_flows"] = [
            f
            for f in process["message_flows"]
            if f.get("from", f.get("from_")) not in gone and f.get("to") not in gone
        ]
    ctx.summaries.append(f'Removed step "{_label(step)}"')


def _move_step(ctx: _Context, op: MoveStep) -> None:
    step = ctx.step(op.step_id, "step_id")
    after = ctx.step(op.after, "after") if op.after is not None else None
    if op.after == op.step_id:
        raise OperationError("invalid", "A step cannot be moved after itself", "after")
    _bridge(ctx, step)
    ctx.steps.pop(ctx.index(step["id"]))
    _insert(ctx, step, op.after, None)
    where = f'after "{_label(after)}"' if after else "to the start"
    ctx.summaries.append(f'Moved step "{_label(step)}" {where}')


def _connect(ctx: _Context, op: Connect) -> None:
    source = ctx.step(op.source, "source")
    target = ctx.step(op.target, "target")
    deps = target.setdefault("depends_on", [])
    if source["id"] not in deps:
        deps.append(source["id"])
    ctx.summaries.append(f'Connected "{_label(source)}" to "{_label(target)}"')


def _disconnect(ctx: _Context, op: Disconnect) -> None:
    source = ctx.step(op.source, "source")
    target = ctx.step(op.target, "target")
    deps = target.get("depends_on", [])
    if source["id"] not in deps:
        raise OperationError(
            "not_found",
            f'Step "{target["id"]}" does not follow step "{source["id"]}"',
            "source",
        )
    target["depends_on"] = [d for d in deps if d != source["id"]]
    ctx.summaries.append(f'Disconnected "{_label(source)}" from "{_label(target)}"')


def _set_step_type(ctx: _Context, op: SetStepType) -> None:
    step = ctx.step(op.step_id, "step_id")
    old = step.get("type", "")
    step["type"] = op.type
    if op.type in _HUMAN_TYPES:
        step.pop("component", None)
    else:
        ctx.component_checks.append(step["id"])
    if old == op.type:
        # The reduced view shows an automated step without a component as
        # ``io``: made ``ai`` again, it stays an automated task.
        ctx.summaries.append(f'Set the type of step "{_label(step)}" to {_TYPE_WORDS[op.type]}')
        return
    ctx.summaries.append(
        f'Changed the type of step "{_label(step)}" from '
        f"{_TYPE_WORDS.get(old, old or 'none')} to {_TYPE_WORDS[op.type]}"
    )


# ---------------------------------------------------------------- lanes
#
# A lane is a ``business_process.participants`` entry, and a step's lane its
# ``performed_by``. Without participants the generator derives the lanes
# (``derived_participants``); the first lane operation makes them participants,
# so the diagram keeps the lanes, names and order it had. A derived lane drawn
# beside participants (a category no participant covers) becomes one when an
# operation names it.


def _lane_participants(ctx: _Context) -> list[dict]:
    """The participants; on a draft without any, the derived lanes made real ones."""
    participants = ctx.process.get("participants")
    if not isinstance(participants, list):
        participants = ctx.process["participants"] = []
    if not participants:
        participants.extend(_derived(ctx))
    return participants


def _derived(ctx: _Context) -> list[dict]:
    try:
        blueprint = Blueprint.model_validate(ctx.blueprint)
    except ValidationError as exc:
        message = f"The blueprint is not valid: {exc.errors()[0]['msg']}"
        raise OperationError("invalid", message) from None
    return [p.model_dump() for p in derived_participants(blueprint)]


def _lane(ctx: _Context, lane_id: str) -> dict:
    participants = _lane_participants(ctx)
    for participant in participants:
        if participant.get("id") == lane_id:
            return participant
    if lane_id in DERIVED_PARTICIPANT_IDS:
        # A derived lane drawn beside the participants: it becomes one of them.
        derived = next((p for p in _derived(ctx) if p["id"] == lane_id), None)
        if derived is not None:
            participants.append(derived)
            return derived
    raise OperationError("not_found", f'There is no lane "{lane_id}"', "lane_id")


def _lane_name(lane: dict) -> str:
    return lane.get("name") or lane.get("id", "")


def _lane_text(value: str) -> str:
    name = value.strip()
    if not name:
        raise OperationError("invalid", "A lane needs a name", "name")
    return name


def _category_lane(participants: list[dict], step_type: str) -> str | None:
    """The participant a step of ``step_type`` without ``performed_by`` is drawn in,
    as the generator picks it (``_lane_for_category``); None for a derived lane."""
    if step_type in ("automated_task", "decision"):
        hit = next((p for p in participants if p.get("kind") == "system"), None)
    else:
        wanted = "human_review" if step_type == "human_review" else "user_task"
        hit = next((p for p in participants if wanted in (p.get("default_lane_for") or [])), None)
    return hit.get("id") if hit else None


def _lane_users(ctx: _Context, lane_id: str) -> list[str]:
    """What is in the lane or names it: steps and manual steps, by their
    ``performed_by`` or, without one, by their type; and message flows."""
    participants = ctx.process.get("participants") or []
    known = {p.get("id") for p in participants}

    def drawn_in(item: dict, step_type: str) -> bool:
        by = item.get("performed_by") or ""
        if by in known:
            return by == lane_id
        return _category_lane(participants, step_type) == lane_id

    users = [f'step "{_label(s)}"' for s in ctx.steps if drawn_in(s, s.get("type", ""))]
    manual_steps = ctx.process.get("manual_steps") or []
    users += [f'step "{_label(m)}"' for m in manual_steps if drawn_in(m, "user_task")]
    for flow in ctx.process.get("message_flows") or []:
        if lane_id in (flow.get("from"), flow.get("to")):
            users.append("a message flow")
    return users


def _add_lane(ctx: _Context, op: AddLane) -> None:
    name = _lane_text(op.name)
    participants = _lane_participants(ctx)
    # Unique among the element ids a message flow can name, and never a
    # derived lane's id, which a step's performed_by may already hold.
    taken = {p.get("id") for p in participants} | set(DERIVED_PARTICIPANT_IDS)
    taken |= {s.get("id") for s in ctx.steps}
    for key in ("manual_steps", "external_parties"):
        taken |= {item.get("id") for item in ctx.process.get(key) or []}
    lane_id = new_step_id(name if _slug(name) else "lane", taken)
    participants.append({"id": lane_id, "name": name, "kind": op.kind, "default_lane_for": []})
    ctx.lanes_added.append(lane_id)
    ctx.summaries.append(f'Added lane "{name}"')


def _rename_lane(ctx: _Context, op: RenameLane) -> None:
    lane = _lane(ctx, op.lane_id)
    name = _lane_text(op.name)
    ctx.summaries.append(f'Renamed lane "{_lane_name(lane)}" to "{name}"')
    lane["name"] = name


def _remove_lane(ctx: _Context, op: RemoveLane) -> None:
    lane = _lane(ctx, op.lane_id)
    users = _lane_users(ctx, op.lane_id)
    if users:
        raise OperationError(
            "lane_in_use",
            f'Lane "{_lane_name(lane)}" is in use ({", ".join(users[:5])}): '
            "move them to another lane first",
            "lane_id",
        )
    ctx.process["participants"] = [p for p in ctx.process["participants"] if p is not lane]
    ctx.lanes_removed.append(op.lane_id)
    ctx.summaries.append(f'Removed lane "{_lane_name(lane)}"')


def _set_step_lane(ctx: _Context, op: SetStepLane) -> None:
    step = ctx.step(op.step_id, "step_id")
    _lane_participants(ctx)
    if op.lane_id is None:
        step.pop("performed_by", None)
        ctx.summaries.append(f'Moved step "{_label(step)}" back to the lane of its type')
        return
    lane = _lane(ctx, op.lane_id)
    step["performed_by"] = lane["id"]
    ctx.summaries.append(f'Moved step "{_label(step)}" to lane "{_lane_name(lane)}"')


# ---------------------------------------------------------------- decisions
#
# A business decision is a ``business_process.decision_points`` entry: the step
# it comes ``after`` and its branches, each a condition and the step it leads
# to, or ``"end"``. The generator draws it as ``Gateway_decision_<id>`` after
# that step. A decision *step* (a ``workflow.steps`` entry of type
# ``decision``) is another thing: a step, edited with the step operations.

_END = "end"
#: The prefix of the element id a decision step is drawn with: ``Gateway_<step id>``
#: and ``Gateway_decision_<decision id>`` must not meet.
_DECISION_STEP_PREFIX = "decision_"


def _decision(ctx: _Context, decision_id: str) -> dict:
    for decision in ctx.process.get("decision_points") or []:
        if decision.get("id") == decision_id:
            return decision
    raise OperationError("not_found", f'There is no decision "{decision_id}"', "decision_id")


def _decision_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise OperationError("invalid", "A decision needs a name", "name")
    return name


def _drawn_step_ids(ctx: _Context) -> set[str]:
    """The steps a branch can lead to: the workflow's and the manual ones."""
    ids = {s.get("id") for s in ctx.steps}
    return ids | {m.get("id") for m in ctx.process.get("manual_steps") or []}


def _branches(ctx: _Context, branches: list[Branch]) -> list[dict]:
    """The branches as stored, or refused: an unknown target (``unknown_step``),
    a blank condition, or all leading to one place (a decision that decides
    nothing). A branch back to an earlier step is checked once all operations
    have run (``_check_loops``)."""
    known = _drawn_step_ids(ctx)
    out = []
    for branch in branches:
        condition = branch.condition.strip()
        if not condition:
            raise OperationError("invalid", "A branch needs a condition", "condition")
        if branch.target != _END and branch.target not in known:
            raise OperationError("unknown_step", f'There is no step "{branch.target}"', "target")
        out.append({"condition": condition, "target": branch.target})
    if len({b["target"] for b in out}) == 1:
        raise OperationError(
            "invalid", "The branches of a decision must not all lead to one place", "branches"
        )
    return out


def _add_decision(ctx: _Context, op: AddDecision) -> None:
    if op.after not in {s.get("id") for s in ctx.steps}:
        raise OperationError("unknown_step", f'There is no step "{op.after}"', "after")
    after = ctx.step(op.after, "after")
    name = _decision_name(op.name)
    decisions = ctx.process.get("decision_points")
    if not isinstance(decisions, list):
        decisions = ctx.process["decision_points"] = []
    if any(d.get("after") == op.after for d in decisions):
        raise OperationError(
            "invalid", f'Step "{_label(after)}" is already followed by a decision', "after"
        )
    branches = _branches(ctx, op.branches)
    taken = {d.get("id") for d in decisions}
    taken |= {
        str(s.get("id"))[len(_DECISION_STEP_PREFIX) :]
        for s in ctx.steps
        if str(s.get("id") or "").startswith(_DECISION_STEP_PREFIX)
    }
    slug_of = name if _slug(name) else "decision"
    decision_id = new_step_id(slug_of, taken)
    decisions.append({"id": decision_id, "name": name, "after": op.after, "branches": branches})
    ctx.summaries.append(f'Added decision "{name}" after step "{_label(after)}"')


def _update_decision(ctx: _Context, op: UpdateDecision) -> None:
    decision = _decision(ctx, op.decision_id)
    old_name = decision.get("name") or decision.get("id", "")
    if op.branches is not None:
        decision["branches"] = _branches(ctx, op.branches)
    if op.name is not None:
        decision["name"] = _decision_name(op.name)
    name = decision.get("name") or decision.get("id", "")
    renamed = f' (was "{old_name}")' if name != old_name else ""
    ctx.summaries.append(f'Changed decision "{name}"{renamed}')


def _remove_decision(ctx: _Context, op: RemoveDecision) -> None:
    decision = _decision(ctx, op.decision_id)
    ctx.process["decision_points"] = [
        d for d in ctx.process["decision_points"] if d is not decision
    ]
    ctx.summaries.append(f'Removed decision "{decision.get("name") or decision.get("id", "")}"')


# ---------------------------------------------------------------- rework and rejection paths

#: A path's outcome: back to a step (``loop_to:<step id>``), or the end.
_LOOP_TO = "loop_to:"


def _path(ctx: _Context, exception_id: str) -> dict:
    for exception in ctx.process.get("exceptions") or []:
        if exception.get("id") == exception_id:
            return exception
    raise OperationError("not_found", f'There is no path "{exception_id}"', "exception_id")


def _path_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise OperationError("invalid", "A path needs a name", "name")
    return name


def _path_words(exception: dict) -> str:
    rework = str(exception.get("outcome") or "").startswith(_LOOP_TO)
    return "rework path" if rework else "rejection path"


def _drawn_order(ctx: _Context) -> list[str]:
    """The steps a path hangs off and leads back to, as ``_Flow`` orders them:
    the workflow's steps, then the manual ones."""
    manual = ctx.process.get("manual_steps") or []
    return [str(s.get("id")) for s in [*ctx.steps, *manual] if isinstance(s, dict)]


def _outcome(ctx: _Context, outcome: str, attached_to: str) -> str:
    """``outcome`` as stored, or refused: neither ``"end"`` nor a loop
    (``invalid``), a loop to an unknown step (``unknown_step``) or to a step
    after ``attached_to`` (``invalid``). A rework path loops back; the
    diagram draws it as a loop flow, so the loop check of decisions leaves it."""
    if outcome == _END:
        return outcome
    if not outcome.startswith(_LOOP_TO):
        raise OperationError(
            "invalid", 'A path ends ("end") or loops back ("loop_to:<step id>")', "outcome"
        )
    target = outcome[len(_LOOP_TO) :]
    order = _drawn_order(ctx)
    if attached_to not in order:
        raise OperationError("unknown_step", f'There is no step "{attached_to}"', "attached_to")
    if target not in order:
        raise OperationError("unknown_step", f'There is no step "{target}"', "outcome")
    if order.index(target) > order.index(attached_to):
        raise OperationError(
            "invalid",
            f'A rework path leads back to an earlier step or the same one, not to "{target}"',
            "outcome",
        )
    return outcome


def _add_rework_path(ctx: _Context, op: AddReworkPath) -> None:
    order = _drawn_order(ctx)
    if op.attached_to not in order:
        raise OperationError("unknown_step", f'There is no step "{op.attached_to}"', "attached_to")
    name = _path_name(op.name)
    outcome = _outcome(ctx, op.outcome, op.attached_to)
    exceptions = ctx.process.get("exceptions")
    if not isinstance(exceptions, list):
        exceptions = ctx.process["exceptions"] = []
    # The generator draws a path as Gateway_exc_<id> and EndEvent_<id>, beside
    # EndEvent_success and each review's EndEvent_rejected_<step id>.
    taken = {e.get("id") for e in exceptions} | {"success"}
    taken |= {f"rejected_{sid}" for sid in order}
    slug_of = name if _slug(name) else "path"
    exception = {
        "id": new_step_id(slug_of, taken),
        "name": name,
        "attached_to": op.attached_to,
        "condition": op.condition.strip(),
        "outcome": outcome,
    }
    exceptions.append(exception)
    step = next(
        s
        for s in [*ctx.steps, *(ctx.process.get("manual_steps") or [])]
        if s.get("id") == op.attached_to
    )
    ctx.summaries.append(f'Added {_path_words(exception)} "{name}" to step "{_label(step)}"')


def _update_rework_path(ctx: _Context, op: UpdateReworkPath) -> None:
    exception = _path(ctx, op.exception_id)
    old_name = exception.get("name") or exception.get("id", "")
    if op.outcome is not None:
        exception["outcome"] = _outcome(ctx, op.outcome, str(exception.get("attached_to") or ""))
    if op.condition is not None:
        exception["condition"] = op.condition.strip()
    if op.name is not None:
        exception["name"] = _path_name(op.name)
    name = exception.get("name") or exception.get("id", "")
    renamed = f' (was "{old_name}")' if name != old_name else ""
    ctx.summaries.append(f'Changed {_path_words(exception)} "{name}"{renamed}')


def _remove_rework_path(ctx: _Context, op: RemoveReworkPath) -> None:
    exception = _path(ctx, op.exception_id)
    ctx.process["exceptions"] = [e for e in ctx.process["exceptions"] if e is not exception]
    name = exception.get("name") or exception.get("id", "")
    ctx.summaries.append(f'Removed {_path_words(exception)} "{name}"')


# ---------------------------------------------------------------- data objects
#
# A data object is an ``artifacts`` entry, drawn as ``DataObjectRef_<id>`` and
# named by its ``label``. A step uses it (``inputs``) or makes it
# (``outputs``); a generated one names the step that makes it in
# ``produced_by``. One step makes a data object: rule 6 of the validator lets
# two make it only when it is flagged ``overwrite``, which the diagram cannot
# show, so a second one is refused.

_ROLE_LISTS = {"input": "inputs", "output": "outputs"}
_DECISION_TYPE = "decision"
_GENERATED = "generated"


def _artifact(ctx: _Context, artifact_id: str) -> dict:
    artifact = (ctx.blueprint.get("artifacts") or {}).get(artifact_id)
    if not isinstance(artifact, dict):
        raise OperationError("not_found", f'There is no data object "{artifact_id}"', "artifact_id")
    return artifact


def _data_name(artifact_id: str, artifact: dict) -> str:
    return artifact.get("label") or artifact_id


def _label_data_object(ctx: _Context, artifact_id: str, value: str, field_name: str) -> None:
    """Sets the artifact's label, or clears it when ``value`` is empty."""
    artifact = (ctx.blueprint.get("artifacts") or {}).get(artifact_id)
    if not isinstance(artifact, dict):
        raise OperationError("not_found", f'There is no artifact "{artifact_id}"', field_name)
    old = artifact.get("label") or ""
    if old == value:
        return
    if value:
        artifact["label"] = value
        ctx.summaries.append(f'Renamed data object "{artifact_id}" to "{value}"')
    else:
        # No label: the diagram names the data object itself again.
        artifact.pop("label", None)
        ctx.summaries.append(f'Cleared the name of data object "{artifact_id}"')


def _rename_data_object(ctx: _Context, op: RenameDataObject) -> None:
    _label_data_object(ctx, op.artifact_id, op.label.strip(), "artifact_id")


def _producers(ctx: _Context, artifact_id: str) -> list[dict]:
    return [s for s in ctx.steps if artifact_id in (s.get("outputs") or [])]


def _users(ctx: _Context, artifact_id: str) -> list[str]:
    """The steps and manual steps that use the data object, by name."""
    users = [_label(s) for s in ctx.steps if artifact_id in (s.get("inputs") or [])]
    manual = ctx.process.get("manual_steps") or []
    return users + [_label(m) for m in manual if artifact_id in (m.get("consumes") or [])]


def _link_data(ctx: _Context, op: LinkData) -> None:
    artifact = _artifact(ctx, op.artifact_id)
    step = ctx.step(op.step_id, "step_id")
    if step.get("type") == _DECISION_TYPE:
        # Drawn as a gateway, which holds no data association.
        raise OperationError(
            "invalid", f'Decision step "{_label(step)}" uses or makes no data', "step_id"
        )
    links = step.setdefault(_ROLE_LISTS[op.role], [])
    name = _data_name(op.artifact_id, artifact)
    verb = "uses" if op.role == "input" else "makes"
    if op.artifact_id in links:
        raise OperationError(
            "already_linked", f'Step "{_label(step)}" already {verb} "{name}"', "artifact_id"
        )
    if op.role == "output":
        other = next((s for s in _producers(ctx, op.artifact_id) if s is not step), None)
        if other is not None:
            raise OperationError(
                "second_producer",
                f'Data object "{name}" is made by step "{_label(other)}"; a data object '
                "is made by one step",
                "artifact_id",
            )
        if artifact.get("source") == _GENERATED:
            artifact["produced_by"] = step["id"]
    links.append(op.artifact_id)
    ctx.summaries.append(f'Step "{_label(step)}" now {verb} data object "{name}"')


def _unlink_data(ctx: _Context, op: UnlinkData) -> None:
    artifact = _artifact(ctx, op.artifact_id)
    step = ctx.step(op.step_id, "step_id")
    key = _ROLE_LISTS[op.role]
    name = _data_name(op.artifact_id, artifact)
    verb = "uses" if op.role == "input" else "makes"
    if op.artifact_id not in (step.get(key) or []):
        raise OperationError(
            "not_found", f'Step "{_label(step)}" does not {verb[:-1]} "{name}"', "artifact_id"
        )
    if op.role == "output":
        others = [s for s in _producers(ctx, op.artifact_id) if s is not step]
        users = _users(ctx, op.artifact_id)
        if not others and users:
            raise OperationError(
                "still_used",
                f'Step "{_label(step)}" is the only one that makes "{name}", which '
                f"{', '.join(users[:5])} use",
                "artifact_id",
            )
        if not others and artifact.get("source") == _GENERATED:
            # A generated data object needs the step that makes it (produced_by),
            # and removing a link never deletes the data object.
            raise OperationError(
                "only_producer",
                f'Step "{_label(step)}" is the only one that makes "{name}"',
                "artifact_id",
            )
        if others and artifact.get("produced_by") == step["id"]:
            artifact["produced_by"] = others[0]["id"]
    step[key] = [a for a in step[key] if a != op.artifact_id]
    ctx.summaries.append(f'Step "{_label(step)}" no longer {verb} data object "{name}"')


def _replace_draft(ctx: _Context, op: ReplaceDraft) -> None:
    ctx.blueprint = copy.deepcopy(op.blueprint)
    ctx.summaries.append(REPLACED_SUMMARY)


def _set_field(ctx: _Context, op: SetField) -> None:
    _FIELD_HANDLERS[op.field](ctx, op)


def _section(ctx: _Context, key: str) -> dict:
    section = ctx.blueprint.get(key)
    if not isinstance(section, dict):
        section = ctx.blueprint[key] = {}
    return section


def _set_use_case_name(ctx: _Context, op: SetField) -> None:
    use_case = _section(ctx, "use_case")
    if not op.value:
        raise OperationError("invalid", "The use case needs a name", "name")
    if use_case.get("name") != op.value:
        use_case["name"] = op.value
        ctx.summaries.append(f'Renamed the use case to "{op.value}"')


def _set_use_case_description(ctx: _Context, op: SetField) -> None:
    use_case = _section(ctx, "use_case")
    if (use_case.get("description") or "") != op.value:
        use_case["description"] = op.value
        ctx.summaries.append("Changed the use case's description")


def _set_goal(ctx: _Context, op: SetField) -> None:
    business = _section(ctx, "business_spec")
    if (business.get("poc_goal") or "") != op.value:
        business["poc_goal"] = op.value
        ctx.summaries.append("Changed the goal of the proof of concept")


def _set_integration_targets(ctx: _Context, op: SetField) -> None:
    technical = _section(ctx, "technical_spec")
    if list(technical.get("integration_targets") or []) == list(op.value):
        return
    technical["integration_targets"] = list(op.value)
    if op.value:
        names = ", ".join(f'"{t}"' for t in op.value)
        ctx.summaries.append(f"Changed the integration targets to {names}")
    else:
        ctx.summaries.append("Removed the integration targets")


def _set_step_component(ctx: _Context, op: SetField) -> None:
    step = ctx.step(op.target, "component")
    if (step.get("component") or "") == op.value:
        return
    if op.value:
        step["component"] = op.value
        ctx.summaries.append(f'Set the component of step "{_label(step)}" to "{op.value}"')
    else:
        step.pop("component", None)
        ctx.summaries.append(f'Removed the component of step "{_label(step)}"')
        ctx.component_checks.append(step["id"])


def _setting_text(value: Any) -> str:
    # As artifact_sync shows a parameter: text as it is, anything else as JSON.
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _set_step_settings(ctx: _Context, op: SetField) -> None:
    step = ctx.step(op.target, "settings")
    old = step.get("parameters") if isinstance(step.get("parameters"), dict) else {}
    # A setting shown as it is keeps its value (a number stays a number).
    parameters = {
        key: old[key] if key in old and _setting_text(old[key]) == text else text
        for key, text in op.value.items()
    }
    if parameters == old:
        return
    step["parameters"] = parameters
    ctx.summaries.append(f'Changed the settings of step "{_label(step)}"')


def _set_artifact_label(ctx: _Context, op: SetField) -> None:
    _label_data_object(ctx, str(op.target), op.value, "data_objects")


_FIELD_HANDLERS: dict[str, Callable[[_Context, SetField], None]] = {
    "use_case_name": _set_use_case_name,
    "use_case_description": _set_use_case_description,
    "goal": _set_goal,
    "integration_targets": _set_integration_targets,
    "step_component": _set_step_component,
    "step_settings": _set_step_settings,
    "artifact_label": _set_artifact_label,
}


_HANDLERS: dict[type, Callable[[_Context, Any], None]] = {
    RenameStep: _rename_step,
    SetStepDescription: _set_step_description,
    AddStep: _add_step,
    RemoveStep: _remove_step,
    MoveStep: _move_step,
    Connect: _connect,
    Disconnect: _disconnect,
    SetStepType: _set_step_type,
    AddLane: _add_lane,
    RenameLane: _rename_lane,
    RemoveLane: _remove_lane,
    SetStepLane: _set_step_lane,
    AddDecision: _add_decision,
    UpdateDecision: _update_decision,
    RemoveDecision: _remove_decision,
    AddReworkPath: _add_rework_path,
    UpdateReworkPath: _update_rework_path,
    RemoveReworkPath: _remove_rework_path,
    RenameDataObject: _rename_data_object,
    LinkData: _link_data,
    UnlinkData: _unlink_data,
    SetField: _set_field,
    ReplaceDraft: _replace_draft,
}
