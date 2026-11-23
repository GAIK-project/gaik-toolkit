/**
 * The goal wizard_api writes into the blueprint it creates with a new session,
 * before the wizard has learned what the solution is for
 * (wizard_api/services/blueprint_service.py). It says something about the
 * draft, not about the user's goal, so it is not shown as one.
 */
export const DRAFT_GOAL_PLACEHOLDER = "Draft flow so BPMN and JSON are editable from the first session.";

const sameText = (text: string) => text.replace(/\s+/g, " ").trim().replace(/\.$/, "").toLowerCase();

/** The blueprint's goal as the user reads it: empty while it is still the draft's placeholder. */
export function shownGoal(goal: string | null | undefined): string {
  const text = (goal ?? "").trim();
  return sameText(text) === sameText(DRAFT_GOAL_PLACEHOLDER) ? "" : text;
}

/**
 * The steps of that same first blueprint, as wizard_api seeds them
 * (default_blueprint_content in wizard_api/services/blueprint_service.py).
 */
const SEED_STEPS: readonly { id: string; name: string; type: string; component?: string; description: string }[] = [
  { id: "input", name: "Input", type: "io", description: "User or system input (placeholder)" },
  { id: "process", name: "Process", type: "ai", component: "LLM", description: "Core GenAI step (placeholder)" },
  { id: "review", name: "Human review", type: "human_review", description: "Optional check before output (placeholder)" },
  { id: "output", name: "Output", type: "io", description: "Returned result (placeholder)" },
];

type SeedCheckedStep = {
  id?: string;
  name?: string;
  type?: string;
  component?: string | null;
  description?: string | null;
  settings?: Record<string, unknown> | null;
};

/**
 * Whether the blueprint is still the seed a new session starts with: nobody
 * has designed anything into it, so its steps are not the solution's. Decided
 * as wizard_api decides it (blueprint_service.is_placeholder): by the steps
 * alone, which must be the seed's, unchanged and in order. The name, the goal
 * and the description do not count: the wizard writes those before the steps.
 */
export function isSeedBlueprint(blueprint: { steps?: readonly SeedCheckedStep[] | null } | null | undefined): boolean {
  const steps = blueprint?.steps;
  if (!steps || steps.length !== SEED_STEPS.length) return false;
  return SEED_STEPS.every((seed, i) => {
    const step = steps[i];
    return (
      step.id === seed.id &&
      step.name === seed.name &&
      step.type === seed.type &&
      (step.component ?? "") === (seed.component ?? "") &&
      (step.description ?? "") === seed.description &&
      Object.keys(step.settings ?? {}).length === 0
    );
  });
}
