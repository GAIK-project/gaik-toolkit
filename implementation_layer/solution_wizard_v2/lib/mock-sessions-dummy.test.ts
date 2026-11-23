import { describe, expect, it } from "vitest";
import {
  createSession,
  defaultBlueprint,
  getSession,
  renameSession,
  resetMockSessions,
} from "@/lib/mock-sessions";
import { chatLeads } from "@/lib/session-start";
import { hasBpmnSpike, shouldShowBpmnSpike, BPMN_VISUAL_STEP } from "@/lib/bpmn-spike";

describe("createSession dummy blueprint", () => {
  it("seeds a placeholder blueprint with several editable steps", () => {
    const bp = defaultBlueprint("Safety report");
    expect(bp.steps.length).toBeGreaterThanOrEqual(3);
    expect(bp.description.toLowerCase()).toContain("placeholder");
    expect(bp.steps.map((s) => s.id)).toEqual([
      "input",
      "process",
      "review",
      "output",
    ]);
  });

  it("new mock sessions get BPMN-capable ids and dummy content", () => {
    resetMockSessions();
    const s = createSession("dev@gaik.local", "dummy demo");
    expect(hasBpmnSpike(s.id)).toBe(true);
    expect(s.blueprint.steps.length).toBeGreaterThanOrEqual(3);
    expect(s.step).toBe(1);
    expect(shouldShowBpmnSpike(s.id, s.step)).toBe(false);
    expect(shouldShowBpmnSpike(s.id, BPMN_VISUAL_STEP)).toBe(true);
  });

  it("a session started from the first message has an empty chat and no checklist", () => {
    resetMockSessions();
    const led = createSession("dev@gaik.local", "Laskun kentät", { chatLed: true });
    expect(led.messages).toEqual([]);
    expect(led.requirements).toEqual({ points: [], answers: [] });
    expect(chatLeads(led.step, led.requirements?.points ?? [])).toBe(true);
    // The default stays the checklist session the mock's own flow relies on.
    const listed = createSession("dev@gaik.local", "Tarkistuslista");
    expect(listed.messages).toHaveLength(1);
    expect(listed.requirements?.points.length).toBeGreaterThan(0);
  });

  it("renames a session and leaves its blueprint's name as it was", () => {
    resetMockSessions();
    const s = createSession("dev@gaik.local", "Vanha nimi");
    expect(renameSession(s.id, "Uusi nimi")?.title).toBe("Uusi nimi");
    expect(getSession(s.id)?.blueprint.name).toBe("Vanha nimi");
    expect(renameSession("ses_missing", "Uusi nimi")).toBeUndefined();
  });
});
