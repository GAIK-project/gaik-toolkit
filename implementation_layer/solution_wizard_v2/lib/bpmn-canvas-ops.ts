/**
 * What an edit on the BPMN canvas means for the blueprint, as an operation.
 *
 * The diagram is drawn from the blueprint, and the server says which element
 * stands for what (`GET /bpmn/mapping`: `{element_id: {kind, blueprint_path}}`,
 * drawn for the same "Show data" mode as the diagram). Only the tasks whose
 * path is `workflow.steps[i]` are steps the canvas can change; the path is an
 * index, so the step's id is read from the steps of the same blueprint.
 * Everything else (start and end, gateways, manual steps, lanes, data objects)
 * is drawn from other parts of the blueprint, and these helpers answer null
 * for it: the canvas offers no edit there.
 *
 * Tier 1: rename, add, move, connect, disconnect and remove a step. Tier 2
 * adds lanes: the mapping names a lane's participant (`participant_id`) and a
 * step's `performed_by`, so a lane can be renamed or removed and a step put
 * in another lane. Business decisions: the mapping names the decision behind
 * a `decision_point` gateway (`decision`), so it can be edited and removed,
 * and a step can get a decision after it.
 */
import { MAX_BRANCHES, MIN_BRANCHES, type BlueprintOperation, type DecisionBranch } from "@/lib/blueprint-ops";

/** A business decision (`business_process.decision_points[i]`), as the mapping names it. */
export type DecisionRef = { id: string; name: string; after: string; branches: DecisionBranch[] };

export type BpmnMapping = Record<
  string,
  {
    kind?: string;
    blueprint_path: string;
    /** A lane's: the id lane operations take (a derived lane's too). */
    participant_id?: string;
    /** A step's: the lane it is put in, "" when its type decides. */
    performed_by?: string;
    /** A business decision's gateway (`decision_point`): the decision it stands for. */
    decision?: DecisionRef;
  }
>;

/** A step of the blueprint the mapping's indexes point into. */
export type StepRef = { id: string; name?: string };

/** An element on the canvas: a flow names its two ends by element id. */
export type CanvasElement = { id: string; type: string; source?: string; target?: string };

/** The type a step added from the canvas gets: the user can change it in the form. */
export const NEW_STEP_TYPE = "user_task" as const;

const STEP_PATH = /^workflow\.steps\[(\d+)\]$/;

/** The id of the step behind `elementId`, or null when it is not a step's task. */
export function stepIdOf(elementId: string, mapping: BpmnMapping, steps: StepRef[]): string | null {
  const entry = Object.prototype.hasOwnProperty.call(mapping, elementId) ? mapping[elementId] : undefined;
  const match = entry && typeof entry.blueprint_path === "string" ? STEP_PATH.exec(entry.blueprint_path) : null;
  if (!match) return null;
  return steps[Number(match[1])]?.id ?? null;
}

/**
 * Whether `elementId` is a decision step: a `workflow.steps` entry the
 * generator draws as a gateway (its mapping kind is the step's type,
 * `decision`). It is a step for the edits that keep it a decision (rename,
 * move, connect, delete), but it has no step type to change.
 */
export function isDecisionStep(elementId: string, mapping: BpmnMapping): boolean {
  const entry = Object.prototype.hasOwnProperty.call(mapping, elementId) ? mapping[elementId] : undefined;
  return Boolean(entry && entry.kind === "decision" && STEP_PATH.test(entry.blueprint_path));
}

/**
 * Whether `steps` are the steps the diagram of `mapping` was drawn from: each
 * `workflow.steps[i]` is drawn as `Activity_<id>` (`Gateway_<id>` for a
 * decision), with the id of the step at that index, and there are as many.
 * While the page has not yet read the version the diagram shows, an index
 * would point at another step, so the canvas offers no edits until it has.
 */
export function mappingFitsSteps(mapping: BpmnMapping, steps: StepRef[]): boolean {
  let count = 0;
  for (const [elementId, entry] of Object.entries(mapping)) {
    const match = typeof entry?.blueprint_path === "string" ? STEP_PATH.exec(entry.blueprint_path) : null;
    if (!match) continue;
    count += 1;
    const step = steps[Number(match[1])];
    if (!step) return false;
    const safe = step.id.replace(/[^\p{L}\p{N}_]/gu, "_");
    if (elementId !== `Activity_${safe}` && elementId !== `Gateway_${safe}`) return false;
  }
  return count === steps.length;
}

/** A finished rename in place: rename_step, or null for an empty or unchanged name or no step. */
export function opForLabelUpdate(
  elementId: string,
  newLabel: string | null | undefined,
  mapping: BpmnMapping,
  steps: StepRef[],
): BlueprintOperation | null {
  const stepId = stepIdOf(elementId, mapping, steps);
  const name = (newLabel ?? "").trim();
  if (!stepId || !name) return null;
  if (steps.find((s) => s.id === stepId)?.name === name) return null;
  return { op: "rename_step", step_id: stepId, name };
}

/** A line drawn with the connect tool: connect, when both ends are steps. */
export function opForConnection(
  sourceId: string,
  targetId: string,
  mapping: BpmnMapping,
  steps: StepRef[],
): BlueprintOperation | null {
  const source = stepIdOf(sourceId, mapping, steps);
  const target = stepIdOf(targetId, mapping, steps);
  if (!source || !target || source === target) return null;
  return { op: "connect", source, target };
}

/** Delete: remove_step for a step's task, remove_decision for a business decision, disconnect for a flow between two steps. */
export function opForDelete(
  element: CanvasElement,
  mapping: BpmnMapping,
  steps: StepRef[],
): BlueprintOperation | null {
  if (element.type === "bpmn:SequenceFlow") {
    if (!element.source || !element.target) return null;
    const source = stepIdOf(element.source, mapping, steps);
    const target = stepIdOf(element.target, mapping, steps);
    return source && target ? { op: "disconnect", source, target } : null;
  }
  const decision = decisionOf(element.id, mapping);
  if (decision) return { op: "remove_decision", decision_id: decision.id };
  const stepId = stepIdOf(element.id, mapping, steps);
  return stepId ? { op: "remove_step", step_id: stepId } : null;
}

/** Whether the canvas offers edits on `element`: a step's task, a business decision, or a flow between two steps. */
export function isOperationElement(element: CanvasElement, mapping: BpmnMapping, steps: StepRef[]): boolean {
  if (element.type === "bpmn:SequenceFlow") return opForDelete(element, mapping, steps) !== null;
  return stepIdOf(element.id, mapping, steps) !== null || decisionOf(element.id, mapping) !== null;
}

/** The palette's "Add step": a new step after the last one. */
export function opForAddStep(name: string, steps: StepRef[]): BlueprintOperation {
  const last = steps[steps.length - 1];
  return last
    ? { op: "add_step", name, type: NEW_STEP_TYPE, after: last.id }
    : { op: "add_step", name, type: NEW_STEP_TYPE };
}

/** A step's "Append step": a new step right after it. */
export function opForAppend(
  elementId: string,
  name: string,
  mapping: BpmnMapping,
  steps: StepRef[],
): BlueprintOperation | null {
  const stepId = stepIdOf(elementId, mapping, steps);
  return stepId ? { op: "add_step", name, type: NEW_STEP_TYPE, after: stepId } : null;
}

/**
 * "Move earlier" and "Move later", in the order of the steps: later goes after
 * the next step, earlier after the one two before. To the start the step is
 * moved with `after: null`, which leaves it depending on nothing, and the old
 * first step is connected after it, so the process stays in one piece. Null
 * where there is no place to move to (the first earlier, the last later).
 */
export function opsForMove(
  elementId: string,
  direction: "earlier" | "later",
  mapping: BpmnMapping,
  steps: StepRef[],
): BlueprintOperation[] | null {
  const stepId = stepIdOf(elementId, mapping, steps);
  if (!stepId) return null;
  const index = steps.findIndex((s) => s.id === stepId);
  if (direction === "later") {
    const next = steps[index + 1];
    return next ? [{ op: "move_step", step_id: stepId, after: next.id }] : null;
  }
  if (index <= 0) return null;
  if (index === 1) {
    return [
      { op: "move_step", step_id: stepId, after: null },
      { op: "connect", source: stepId, target: steps[0].id },
    ];
  }
  return [{ op: "move_step", step_id: stepId, after: steps[index - 2].id }];
}

function entryOf(elementId: string, mapping: BpmnMapping) {
  return Object.prototype.hasOwnProperty.call(mapping, elementId) ? mapping[elementId] : undefined;
}

/** The participant id behind the lane `elementId`, or null when it is no lane the mapping names. */
export function laneIdOf(elementId: string, mapping: BpmnMapping): string | null {
  const entry = entryOf(elementId, mapping);
  return entry?.kind === "lane" && entry.participant_id ? entry.participant_id : null;
}

/** The lane a step is put in (its `performed_by`); "" when the step's type decides its lane. */
export function performedByOf(elementId: string, mapping: BpmnMapping): string {
  return entryOf(elementId, mapping)?.performed_by ?? "";
}

/**
 * A step dragged from the lane `fromLaneId` into the lane `toLaneId` (both
 * element ids): set_step_lane with the target lane's participant. Null when it
 * stays in its lane, or either is not a step or a lane the mapping names.
 */
export function opForStepLane(
  stepElementId: string,
  toLaneId: string,
  fromLaneId: string | null,
  mapping: BpmnMapping,
  steps: StepRef[],
): BlueprintOperation | null {
  if (toLaneId === fromLaneId) return null;
  const stepId = stepIdOf(stepElementId, mapping, steps);
  const laneId = laneIdOf(toLaneId, mapping);
  return stepId && laneId ? { op: "set_step_lane", step_id: stepId, lane_id: laneId } : null;
}

/** A lane's name typed in place: rename_lane, or null for an empty or unchanged name or no lane. */
export function opForLaneRename(
  laneElementId: string,
  newName: string | null | undefined,
  oldName: string | null | undefined,
  mapping: BpmnMapping,
): BlueprintOperation | null {
  const laneId = laneIdOf(laneElementId, mapping);
  const name = (newName ?? "").trim();
  if (!laneId || !name || name === (oldName ?? "").trim()) return null;
  return { op: "rename_lane", lane_id: laneId, name };
}

/**
 * The business decision behind `elementId`: a gateway the mapping names as a
 * `decision_point` with its decision. Null for anything else, the approval
 * gateway and the other gateways the generator draws by itself included, and
 * for a decision step (a `workflow.steps` entry drawn as a gateway).
 */
export function decisionOf(elementId: string, mapping: BpmnMapping): DecisionRef | null {
  const entry = entryOf(elementId, mapping);
  const decision = entry?.kind === "decision_point" ? entry.decision : undefined;
  return decision && typeof decision.id === "string" && decision.id ? decision : null;
}

/** Whether a business decision already follows the step: a step has one at most. */
export function stepHasDecision(stepId: string, mapping: BpmnMapping): boolean {
  return Object.values(mapping).some((entry) => entry?.kind === "decision_point" && entry.decision?.after === stepId);
}

/** What the branch dialog holds. */
export type DecisionValues = { name: string; branches: DecisionBranch[] };

/** What keeps the dialog's values from being a decision, or null when they are one. */
export type DecisionProblem = "name" | "count" | "condition" | "target" | "same_target";

export function decisionProblem(values: DecisionValues): DecisionProblem | null {
  if (!values.name.trim()) return "name";
  const { branches } = values;
  if (branches.length < MIN_BRANCHES || branches.length > MAX_BRANCHES) return "count";
  if (branches.some((b) => !b.condition.trim())) return "condition";
  if (branches.some((b) => !b.target)) return "target";
  // Every branch to one place decides nothing (wizard_api refuses it too).
  if (new Set(branches.map((b) => b.target)).size === 1) return "same_target";
  return null;
}

/**
 * The dialog's values as an operation: add_decision after a step, or
 * update_decision (name and branches) for a decision; null while they are no
 * decision (`decisionProblem`).
 */
export function opForDecision(
  values: DecisionValues,
  of: { after: string } | { decision: DecisionRef },
): BlueprintOperation | null {
  if (decisionProblem(values)) return null;
  const name = values.name.trim();
  const branches = values.branches.map((b) => ({ condition: b.condition.trim(), target: b.target }));
  return "after" in of
    ? { op: "add_decision", after: of.after, name, branches }
    : { op: "update_decision", decision_id: of.decision.id, name, branches };
}
