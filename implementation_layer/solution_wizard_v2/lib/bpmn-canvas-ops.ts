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
 * Tier 1: rename, add, move, connect, disconnect and remove a step. Later
 * tiers add their element kinds here in the same way.
 */
import type { BlueprintOperation } from "@/lib/blueprint-ops";

export type BpmnMapping = Record<string, { kind?: string; blueprint_path: string }>;

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

/** Delete: remove_step for a step's task, disconnect for a flow between two steps. */
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
  const stepId = stepIdOf(element.id, mapping, steps);
  return stepId ? { op: "remove_step", step_id: stepId } : null;
}

/** Whether the canvas offers edits on `element`: a step's task, or a flow between two steps. */
export function isOperationElement(element: CanvasElement, mapping: BpmnMapping, steps: StepRef[]): boolean {
  if (element.type === "bpmn:SequenceFlow") return opForDelete(element, mapping, steps) !== null;
  return stepIdOf(element.id, mapping, steps) !== null;
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
