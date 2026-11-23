import { describe, expect, it } from "vitest";
import {
  baseIsStale,
  blueprintBaseTag,
  blueprintDraftProblem,
  blueprintPayload,
  blueprintPayloadKey,
  renameSetting,
  restoreStep,
} from "@/lib/blueprint-draft";
import type { Blueprint, BlueprintStep } from "@/lib/mock-sessions";

// The Blueprint form saves by itself. These pin what a save writes, when a
// draft counts as changed, and when it may not be saved yet.

const base: Blueprint = {
  name: "Invoice classification",
  description: "Classify invoices",
  goal: "Faster handling",
  integration_targets: ["finance_system"],
  steps: [
    { id: "ingest", name: "Invoice intake", type: "io" },
    { id: "classify", name: "Classification", type: "ai", component: "LLM", settings: { model: "gpt-4o" } },
  ],
};

describe("blueprintPayload", () => {
  it("trims text and leaves out empty optional step fields", () => {
    const payload = blueprintPayload({
      ...base,
      name: "  Invoice classification ",
      steps: [
        { id: "ingest", name: " Invoice intake ", type: "io", component: "  ", description: "" },
        { id: "classify", name: "Classification", type: "ai", settings: { " model ": " gpt-4o ", "": "x" } },
      ],
    });
    expect(payload.name).toBe("Invoice classification");
    expect(payload.steps[0]).toEqual({ id: "ingest", name: "Invoice intake", type: "io" });
    expect(payload.steps[1].settings).toEqual({ model: "gpt-4o" });
  });

  it("keeps what the form does not edit, so a save does not drop what the diagram synced", () => {
    const payload = blueprintPayload({
      ...base,
      data_objects: { DataObjectRef_1: "Invoice" },
      gateways: [{ id: "Gateway_1", name: "Approved?", type: "exclusive" }],
    });
    expect(payload.integration_targets).toEqual(["finance_system"]);
    expect(payload.data_objects).toEqual({ DataObjectRef_1: "Invoice" });
    expect(payload.gateways).toHaveLength(1);
  });
});

describe("blueprintPayloadKey", () => {
  it("is the same for the same content in another key order or with spaces a save trims", () => {
    const reordered: Blueprint = {
      steps: structuredClone(base.steps),
      integration_targets: ["finance_system"],
      goal: "Faster handling ",
      description: "Classify invoices",
      name: "Invoice classification",
    };
    expect(blueprintPayloadKey(reordered)).toBe(blueprintPayloadKey(base));
  });

  it("changes with an edit a save would write", () => {
    const edited = { ...base, steps: [{ ...base.steps[0], name: "Intake" }, base.steps[1]] };
    expect(blueprintPayloadKey(edited)).not.toBe(blueprintPayloadKey(base));
  });
});

describe("blueprintDraftProblem", () => {
  it("lets a named blueprint with named steps be saved", () => {
    expect(blueprintDraftProblem(base)).toBeNull();
    expect(blueprintDraftProblem({ ...base, steps: [] })).toBeNull();
  });

  it("holds a save while a step has no name, and says so before the blueprint's own name", () => {
    const unnamedStep = { ...base, steps: [...base.steps, { id: "new", name: "  ", type: "io" as const }] };
    expect(blueprintDraftProblem(unnamedStep)).toBe("stepName");
    expect(blueprintDraftProblem({ ...unnamedStep, name: "" })).toBe("stepName");
    expect(blueprintDraftProblem({ ...base, name: " " })).toBe("name");
  });
});

describe("renameSetting", () => {
  const settings = { model: "gpt-4o", temperature: "0", language: "fi" };

  it("renames a key at its place and keeps its value", () => {
    const next = renameSetting(settings, "temperature", " temp ");
    expect(Object.entries(next)).toEqual([
      ["model", "gpt-4o"],
      ["temp", "0"],
      ["language", "fi"],
    ]);
  });

  it("keeps the old key when the new one is already another setting's", () => {
    // Taking it would write this value over the other setting's, or drop one of the two.
    expect(renameSetting(settings, "temperature", "model")).toBe(settings);
    expect(renameSetting(settings, "temperature", " language ")).toBe(settings);
  });

  it("keeps the old key when the new one is empty, the same, or the setting is gone", () => {
    expect(renameSetting(settings, "temperature", "  ")).toBe(settings);
    expect(renameSetting(settings, "temperature", "temperature")).toBe(settings);
    expect(renameSetting(settings, "removed", "anything")).toBe(settings);
  });
});

describe("restoreStep", () => {
  const removed: BlueprintStep = { id: "extract", name: "Data extraction", type: "ai" };

  it("puts a removed step back where it was", () => {
    expect(restoreStep(base.steps, removed, 1).map((s) => s.id)).toEqual(["ingest", "extract", "classify"]);
  });

  it("puts it last when the list got shorter meanwhile, and never twice", () => {
    expect(restoreStep([base.steps[0]], removed, 5).map((s) => s.id)).toEqual(["ingest", "extract"]);
    const again = restoreStep([base.steps[0], removed], removed, 0);
    expect(again.map((s) => s.id)).toEqual(["ingest", "extract"]);
  });
});


describe("blueprintBaseTag", () => {
  const bp: Blueprint = {
    name: "Demo",
    description: "",
    goal: "",
    steps: [{ id: "s1", name: "Read", type: "io" }],
  };

  it("is the same for the same saved content, whatever the spacing or key order", () => {
    const same = { goal: "", steps: [{ type: "io", name: " Read ", id: "s1" }], description: "", name: "Demo" };
    expect(blueprintBaseTag(same as unknown as Blueprint)).toBe(blueprintBaseTag(bp));
  });

  it("differs when the agent added a step", () => {
    const newer = { ...bp, steps: [...bp.steps, { id: "s2", name: "Check", type: "human_review" } as BlueprintStep] };
    expect(blueprintBaseTag(newer)).not.toBe(blueprintBaseTag(bp));
  });

  it("refuses a save made on another version, and lets one without a base through", () => {
    const newer = { ...bp, name: "Demo 2" };
    expect(baseIsStale(blueprintBaseTag(bp), newer)).toBe(true);
    expect(baseIsStale(blueprintBaseTag(bp), bp)).toBe(false);
    // The user's own choice to keep theirs, and a save as the page closes, send none.
    expect(baseIsStale(undefined, newer)).toBe(false);
    expect(baseIsStale("", newer)).toBe(false);
  });
});
