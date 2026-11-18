/**
 * What the BPMN editor's step panel shows of a step, and the operations a
 * save of it sends (components/bpmn-step-panel).
 *
 * The page shows a step's type in its own words (`io`, `ai`, `human_review`);
 * an operation sets the blueprint's (`user_task`, `automated_task`,
 * `human_review`). An automated task without a component reads as `io` on the
 * page, so a step the last edit left needing a component (wizard_api's
 * `needs_attention`) is an AI step here whatever the page still shows.
 */
import type { BlueprintOperation, StepType } from "@/lib/blueprint-ops";
import type { BlueprintStep, BlueprintStepType } from "@/lib/mock-sessions";

/** `WorkflowStep.description` in solution_wizard's blueprint, and `MAX_DESCRIPTION_CHARS` in wizard_api. */
export const MAX_STEP_DESCRIPTION = 2000;
/** A step's name: `MAX_NAME_CHARS` in wizard_api. */
export const MAX_STEP_NAME = 200;

/** The three types a step can be given, in the order the menu and the panel list them. */
export const STEP_OP_TYPES: StepType[] = ["user_task", "automated_task", "human_review"];

const OP_TYPE: Record<BlueprintStepType, StepType> = {
  io: "user_task",
  ai: "automated_task",
  human_review: "human_review",
};

/** The page's type for a type an operation sets: the words the step list uses. */
export const PAGE_TYPE: Record<StepType, BlueprintStepType> = {
  user_task: "io",
  automated_task: "ai",
  human_review: "human_review",
};

export function opStepType(type: BlueprintStepType): StepType {
  return OP_TYPE[type] ?? "user_task";
}

/** wizard_api's `needs_attention` entry for an automated step without a component. */
export function needsComponentEntry(stepId: string): string {
  return `${stepId}: needs a component`;
}

/** The fields a save compares: what the panel shows, for one step. */
export type PanelValues = { stepId: string; name: string; description: string; type: StepType };

export type PanelFields = PanelValues & { needsComponent: boolean };

/**
 * The panel's fields for `step`. `needsComponent` is true for an AI step the
 * last edit's `needsAttention` lists as needing a component, and for an AI
 * step without one in the blueprint the page has.
 */
export function panelFields(step: BlueprintStep, needsAttention: string[]): PanelFields {
  const listed = needsAttention.includes(needsComponentEntry(step.id));
  const type = listed ? "automated_task" : opStepType(step.type);
  return {
    stepId: step.id,
    name: step.name,
    description: step.description ?? "",
    type,
    needsComponent: listed || (type === "automated_task" && !step.component),
  };
}

const clean = (text: string, max: number) => text.trim().slice(0, max);

/**
 * The operations that take `before` to `after`, in the order rename,
 * description, type: only the fields that changed. Names and descriptions
 * are compared and sent trimmed and within their limits; a name is never
 * emptied. Nothing when the two are about different steps.
 */
export function panelOps(before: PanelValues, after: PanelValues): BlueprintOperation[] {
  if (before.stepId !== after.stepId) return [];
  const stepId = before.stepId;
  const ops: BlueprintOperation[] = [];
  const name = clean(after.name, MAX_STEP_NAME);
  if (name && name !== before.name.trim()) ops.push({ op: "rename_step", step_id: stepId, name });
  const description = clean(after.description, MAX_STEP_DESCRIPTION);
  if (description !== before.description.trim()) {
    ops.push({ op: "set_step_description", step_id: stepId, description });
  }
  if (after.type !== before.type) ops.push({ op: "set_step_type", step_id: stepId, type: after.type });
  return ops;
}

/** What the user typed into a step's panel and an edit carried: kept over a refusal, sent again later. */
export type KeptPanelEdit = { stepId: string; name?: string; description?: string };

/**
 * The typed part of a refused edit: the name and the description it set for
 * one step. Null for anything else (a type alone is one click to make again).
 */
export function keptPanelEdit(ops: BlueprintOperation[]): KeptPanelEdit | null {
  let kept: KeptPanelEdit | null = null;
  for (const op of ops) {
    if (op.op !== "rename_step" && op.op !== "set_step_description" && op.op !== "set_step_type") return null;
    if (kept && kept.stepId !== op.step_id) return null;
    kept ??= { stepId: op.step_id };
    if (op.op === "rename_step") kept.name = op.name;
    if (op.op === "set_step_description") kept.description = op.description;
  }
  return kept && (kept.name !== undefined || kept.description !== undefined) ? kept : null;
}
