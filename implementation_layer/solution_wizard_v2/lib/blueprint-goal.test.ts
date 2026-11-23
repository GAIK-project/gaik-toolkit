import { describe, expect, it } from "vitest";
import { DRAFT_GOAL_PLACEHOLDER, isSeedBlueprint, shownGoal } from "./blueprint-goal";
import { defaultBlueprint } from "./mock-sessions";

describe("shownGoal", () => {
  it("leaves out the placeholder a new session's blueprint carries", () => {
    expect(shownGoal(DRAFT_GOAL_PLACEHOLDER)).toBe("");
    expect(shownGoal("Draft flow so BPMN and JSON are editable from the first session.")).toBe("");
    expect(shownGoal("  draft flow so BPMN and JSON are editable\nfrom the first session  ")).toBe("");
  });

  it("keeps a goal the wizard or the user wrote", () => {
    expect(shownGoal(" Halve the invoice handling time. ")).toBe("Halve the invoice handling time.");
    expect(shownGoal("Draft flow for the invoice team")).toBe("Draft flow for the invoice team");
  });

  it("is empty when there is no goal", () => {
    expect(shownGoal("")).toBe("");
    expect(shownGoal(null)).toBe("");
    expect(shownGoal(undefined)).toBe("");
  });
});

describe("isSeedBlueprint", () => {
  it("knows the blueprint a new session starts with, whatever it is called", () => {
    expect(isSeedBlueprint(defaultBlueprint("Invoices"))).toBe(true);
    const renamed = { ...defaultBlueprint(""), name: "Other", goal: "Halve the handling time.", description: "" };
    expect(isSeedBlueprint(renamed)).toBe(true);
    // The form writes an empty settings object and an empty component into a step it has touched.
    const seed = defaultBlueprint("x");
    expect(
      isSeedBlueprint({ ...seed, steps: seed.steps.map((s) => ({ ...s, component: s.component ?? "", settings: {} })) }),
    ).toBe(true);
  });

  it("takes any change to the steps as a design", () => {
    const seed = defaultBlueprint("x");
    const withStep = (index: number, change: object) => ({
      ...seed,
      steps: seed.steps.map((s, i) => (i === index ? { ...s, ...change } : s)),
    });
    expect(isSeedBlueprint(withStep(1, { name: "Extract the invoice fields" }))).toBe(false);
    expect(isSeedBlueprint(withStep(1, { component: "DataExtractor" }))).toBe(false);
    expect(isSeedBlueprint(withStep(0, { description: "The invoice as a PDF" }))).toBe(false);
    expect(isSeedBlueprint(withStep(2, { settings: { reviewer: "finance" } }))).toBe(false);
    expect(isSeedBlueprint({ ...seed, steps: seed.steps.slice(0, 3) })).toBe(false);
    expect(isSeedBlueprint({ ...seed, steps: [...seed.steps].reverse() })).toBe(false);
  });

  it("is false without a blueprint or steps", () => {
    expect(isSeedBlueprint(null)).toBe(false);
    expect(isSeedBlueprint(undefined)).toBe(false);
    expect(isSeedBlueprint({ steps: [] })).toBe(false);
    expect(isSeedBlueprint({})).toBe(false);
  });
});
