import { describe, expect, it } from "vitest";
import { blueprintKey, draftOnBlueprintChange } from "@/lib/blueprint-sync";
import type { Blueprint } from "@/lib/mock-sessions";

// The Plan and Blueprint tabs kept the blueprint the page first rendered with,
// while the agent wrote newer versions from the chat; a save from there wrote
// the old one back. These pin when the editor takes the newer blueprint and
// when it keeps the user's unsaved edits.

const placeholder: Blueprint = { name: "Uusi", description: "", goal: "", steps: [] };
const agents: Blueprint = {
  name: "Invoice extraction",
  description: "",
  goal: "Extract fields",
  steps: [{ id: "s1", name: "Parse", type: "ai" }],
};

describe("blueprintKey", () => {
  it("is equal for equal content in different objects", () => {
    expect(blueprintKey(structuredClone(agents))).toBe(blueprintKey(agents));
  });
});

describe("draftOnBlueprintChange", () => {
  it("takes the new blueprint when the draft has no edits", () => {
    const r = draftOnBlueprintChange(structuredClone(placeholder), placeholder, agents);
    expect(r.draft).toEqual(agents);
    expect(r.draft).not.toBe(agents);
    expect(r.changedElsewhere).toBe(false);
  });

  it("keeps unsaved edits and says the blueprint changed elsewhere", () => {
    const edited = { ...placeholder, name: "Mine" };
    const r = draftOnBlueprintChange(edited, placeholder, agents);
    expect(r.draft).toBe(edited);
    expect(r.changedElsewhere).toBe(true);
  });

  it("does not warn when the change is the draft just saved", () => {
    const saved = { ...placeholder, name: "Mine" };
    const r = draftOnBlueprintChange(structuredClone(saved), placeholder, saved);
    expect(r.draft).toEqual(saved);
    expect(r.changedElsewhere).toBe(false);
  });
});
