import { describe, expect, it } from "vitest";
import {
  MAX_STEP_DESCRIPTION,
  MAX_STEP_NAME,
  keptPanelEdit,
  needsComponentEntry,
  opStepType,
  panelFields,
  panelOps,
  type PanelValues,
} from "@/lib/step-panel-model";
import type { BlueprintStep } from "@/lib/mock-sessions";

const before: PanelValues = {
  stepId: "extract",
  name: "Extract fields",
  description: "Reads the invoice",
  type: "automated_task",
};

describe("panelOps", () => {
  it("panelOps emits only the fields that changed", () => {
    expect(panelOps(before, { ...before })).toEqual([]);
    expect(panelOps(before, { ...before, name: "Read the fields" })).toEqual([
      { op: "rename_step", step_id: "extract", name: "Read the fields" },
    ]);
    expect(panelOps(before, { ...before, description: "Reads every invoice" })).toEqual([
      { op: "set_step_description", step_id: "extract", description: "Reads every invoice" },
    ]);
    expect(panelOps(before, { ...before, type: "human_review" })).toEqual([
      { op: "set_step_type", step_id: "extract", type: "human_review" },
    ]);
    // All three, in the order rename, description, type.
    expect(
      panelOps(before, { ...before, name: "Check", description: "", type: "human_review" }).map((o) => o.op),
    ).toEqual(["rename_step", "set_step_description", "set_step_type"]);
  });

  it("compares the trimmed text: spaces around a name or a description are no change", () => {
    expect(panelOps(before, { ...before, name: "  Extract fields ", description: "Reads the invoice\n" })).toEqual([]);
    expect(panelOps(before, { ...before, name: " New name " })).toEqual([
      { op: "rename_step", step_id: "extract", name: "New name" },
    ]);
  });

  it("never renames a step to nothing", () => {
    expect(panelOps(before, { ...before, name: "   " })).toEqual([]);
  });

  it("never sends more than the field limits", () => {
    const long = "x".repeat(MAX_STEP_DESCRIPTION + 50);
    const [op] = panelOps(before, { ...before, description: long });
    expect(op).toEqual({ op: "set_step_description", step_id: "extract", description: "x".repeat(MAX_STEP_DESCRIPTION) });
    const [rename] = panelOps(before, { ...before, name: "n".repeat(MAX_STEP_NAME + 5) });
    expect(rename).toEqual({ op: "rename_step", step_id: "extract", name: "n".repeat(MAX_STEP_NAME) });
  });

  it("sends nothing when the two are about different steps", () => {
    expect(panelOps(before, { ...before, stepId: "review", name: "Other" })).toEqual([]);
  });
});

describe("panelFields", () => {
  const ai: BlueprintStep = { id: "classify", name: "Classify", type: "ai", component: "LLM", description: "Sorts" };

  it("needsComponent is true for an AI step listed in needsAttention", () => {
    const fields = panelFields(ai, ["classify: needs a component"]);
    expect(fields).toEqual({
      stepId: "classify",
      name: "Classify",
      description: "Sorts",
      type: "automated_task",
      needsComponent: true,
    });
    // Another step's entry, or another rule's, says nothing about this one.
    expect(panelFields(ai, ["extract: needs a component", "Rule 9: classify"]).needsComponent).toBe(false);
  });

  it("needsComponent is true for an AI step without a component in the loaded blueprint", () => {
    expect(panelFields({ id: "classify", name: "Classify", type: "ai" }, []).needsComponent).toBe(true);
    expect(panelFields(ai, []).needsComponent).toBe(false);
  });

  it("a step the last edit made an AI step is one, even where the page still shows it as input or output", () => {
    // Without a component an automated task can read as io until the page has the newer version.
    const io: BlueprintStep = { id: "review", name: "Review", type: "io" };
    expect(panelFields(io, ["review: needs a component"])).toMatchObject({
      type: "automated_task",
      needsComponent: true,
    });
  });

  it("maps each type the page shows to the type an operation sets", () => {
    expect(panelFields({ id: "a", name: "A", type: "io" }, [])).toMatchObject({ type: "user_task", needsComponent: false });
    expect(panelFields({ id: "a", name: "A", type: "human_review" }, [])).toMatchObject({
      type: "human_review",
      needsComponent: false,
    });
    expect(panelFields({ id: "a", name: "A", type: "io" }, []).description).toBe("");
    expect(opStepType("io")).toBe("user_task");
    expect(opStepType("ai")).toBe("automated_task");
    expect(opStepType("human_review")).toBe("human_review");
  });

  it("names the needs-attention entry of a step", () => {
    expect(needsComponentEntry("classify")).toBe("classify: needs a component");
  });
});

describe("keptPanelEdit", () => {
  it("keeps what the user gave one step: its name, its description and its type", () => {
    expect(
      keptPanelEdit([
        { op: "rename_step", step_id: "extract", name: "Read" },
        { op: "set_step_description", step_id: "extract", description: "Reads" },
        { op: "set_step_type", step_id: "extract", type: "human_review" },
      ]),
    ).toEqual({ stepId: "extract", name: "Read", description: "Reads", type: "human_review" });
    // A type picked alone is kept too: it is made on the newer version.
    expect(keptPanelEdit([{ op: "set_step_type", step_id: "extract", type: "user_task" }])).toEqual({
      stepId: "extract",
      type: "user_task",
    });
    expect(keptPanelEdit([{ op: "rename_step", step_id: "extract", name: "Read" }])).toEqual({
      stepId: "extract",
      name: "Read",
    });
  });

  it("keeps nothing for other edits or edits of two steps", () => {
    expect(keptPanelEdit([{ op: "remove_step", step_id: "extract" }])).toBeNull();
    expect(
      keptPanelEdit([
        { op: "rename_step", step_id: "extract", name: "Read" },
        { op: "rename_step", step_id: "review", name: "Check" },
      ]),
    ).toBeNull();
    expect(keptPanelEdit([])).toBeNull();
  });
});
