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

/** What the user gave a step in its panel or the type menu: kept over a refusal, sent again later. */
export type KeptPanelEdit = { stepId: string; name?: string; description?: string; type?: StepType };

/**
 * What a refused edit set for each step: its name, description and type, one
 * entry a step in the order the edit named them. Empty when the edit did
 * anything else as well: only these fields are made again later.
 */
export function keptPanelEdits(ops: BlueprintOperation[]): KeptPanelEdit[] {
  const kept = new Map<string, KeptPanelEdit>();
  for (const op of ops) {
    if (op.op !== "rename_step" && op.op !== "set_step_description" && op.op !== "set_step_type") return [];
    const edit = kept.get(op.step_id) ?? { stepId: op.step_id };
    if (op.op === "rename_step") edit.name = op.name;
    if (op.op === "set_step_description") edit.description = op.description;
    if (op.op === "set_step_type") edit.type = op.type;
    kept.set(op.step_id, edit);
  }
  return [...kept.values()];
}

/**
 * `kept` with `edits` merged in, one entry a step: an edit of a step already
 * kept adds its fields to that entry, and the edits of other steps stay. The
 * fields of `edits` win, unless they are `older` than what is kept (an edit
 * refused after the user had typed more for the same step meanwhile).
 */
export function mergeKeptEdits(
  kept: KeptPanelEdit[],
  edits: KeptPanelEdit[],
  { older = false }: { older?: boolean } = {},
): KeptPanelEdit[] {
  const merged = new Map(kept.map((edit) => [edit.stepId, { ...edit }]));
  for (const edit of edits) {
    const current = merged.get(edit.stepId);
    merged.set(edit.stepId, current ? (older ? { ...edit, ...current } : { ...current, ...edit }) : { ...edit });
  }
  return [...merged.values()];
}

/**
 * The kept edits as operations on the steps of a newer version: each step's
 * fields against what that step has now (`fieldsOf`). A step that is not
 * there any more is `gone`; a step that is a decision on that version
 * (`isDecision`) keeps its type, and a type kept for it is in `decisionTypes`:
 * set_step_type would turn its gateway into a task.
 */
export function keptEditOps<S extends { id: string }>(
  kept: KeptPanelEdit[],
  steps: S[],
  fieldsOf: (step: S) => PanelValues,
  isDecision: (stepId: string) => boolean,
): { ops: BlueprintOperation[]; gone: KeptPanelEdit[]; decisionTypes: { edit: KeptPanelEdit; step: S }[] } {
  const ops: BlueprintOperation[] = [];
  const gone: KeptPanelEdit[] = [];
  const decisionTypes: { edit: KeptPanelEdit; step: S }[] = [];
  for (const edit of kept) {
    const step = steps.find((s) => s.id === edit.stepId);
    if (!step) {
      gone.push(edit);
      continue;
    }
    const before = fieldsOf(step);
    const decision = isDecision(step.id);
    if (decision && edit.type !== undefined) decisionTypes.push({ edit, step });
    ops.push(
      ...panelOps(before, {
        ...before,
        name: edit.name ?? before.name,
        description: edit.description ?? before.description,
        type: decision ? before.type : (edit.type ?? before.type),
      }),
    );
  }
  return { ops, gone, decisionTypes };
}

/**
 * Whether an edit refused as changed elsewhere on `refusedBase` waits for the
 * page to read a newer version. Not when the page already has one
 * (`pageVersion`, read while the edit was on its way): no newer one may come.
 */
export function waitsForVersion(refusedBase: number | null | undefined, pageVersion: number | null | undefined): boolean {
  if (typeof refusedBase !== "number" || typeof pageVersion !== "number") return true;
  return pageVersion <= refusedBase;
}
