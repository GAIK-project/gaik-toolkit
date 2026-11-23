import { describe, expect, it } from "vitest";
import { BPMN_VISUAL_STEP, POC_STEP } from "@/lib/mock-sessions";
import {
  nextTabForStepChange,
  parseTabParam,
  tabWhenPocLocks,
  tabForStep,
  visibleTabs,
} from "@/lib/workspace-tab-follow";

describe("visibleTabs", () => {
  it("lists Blueprint, Työnkulku and PoC in the wizard's order once the diagram exists", () => {
    expect(visibleTabs(true)).toEqual(["json", "flow", "poc"]);
  });

  it("leaves Työnkulku out before the diagram exists", () => {
    expect(visibleTabs(false)).toEqual(["json", "poc"]);
  });
});

describe("tabForStep", () => {
  it("opens the blueprint before the BPMN phase", () => {
    expect(tabForStep(5, false)).toBe("json");
    expect(tabForStep(BPMN_VISUAL_STEP - 1, true)).toBe("json");
  });

  it("opens the diagram in the BPMN phases when it is shown", () => {
    expect(tabForStep(BPMN_VISUAL_STEP, true)).toBe("flow");
    expect(tabForStep(POC_STEP - 1, true)).toBe("flow");
  });

  it("falls back to the blueprint in the BPMN phases when there is no diagram", () => {
    expect(tabForStep(BPMN_VISUAL_STEP, false)).toBe("json");
  });

  it("opens the PoC from the PoC step to the end", () => {
    expect(tabForStep(POC_STEP, true)).toBe("poc");
    expect(tabForStep(13, false)).toBe("poc");
  });
});

describe("parseTabParam", () => {
  it("reads the tab names the URL may carry", () => {
    expect(parseTabParam("poc")).toBe("poc");
    expect(parseTabParam("flow")).toBe("flow");
    expect(parseTabParam("blueprint")).toBe("json");
    expect(parseTabParam("JSON")).toBe("json");
  });

  it("ignores a missing or unknown value", () => {
    expect(parseTabParam(undefined)).toBeUndefined();
    expect(parseTabParam("plan")).toBeUndefined();
  });
});

// Bug this covers (#138): the customer reviewer completed a whole PoC via chat alone —
// the workspace panel never followed, so nothing was ever visible ("the chat and this
// user interface are not in sync"). These pin the exact milestone crossings that must
// switch tabs, and the cases that must NOT.

describe("nextTabForStepChange", () => {
  it("does nothing when the step doesn't move", () => {
    expect(nextTabForStepChange(5, 5)).toBeNull();
  });

  it("does nothing when the step regresses (e.g. a gate rejection)", () => {
    expect(nextTabForStepChange(BPMN_VISUAL_STEP, BPMN_VISUAL_STEP - 1)).toBeNull();
  });

  it("does nothing for a forward step that doesn't cross a milestone", () => {
    expect(nextTabForStepChange(1, 2)).toBeNull();
  });

  it("switches to flow when crossing into the BPMN-visual step", () => {
    expect(nextTabForStepChange(BPMN_VISUAL_STEP - 1, BPMN_VISUAL_STEP)).toBe("flow");
  });

  it("does not re-trigger flow once already past the BPMN-visual step", () => {
    expect(nextTabForStepChange(BPMN_VISUAL_STEP, BPMN_VISUAL_STEP + 1)).toBeNull();
  });

  it("switches to poc when crossing into the PoC step", () => {
    expect(nextTabForStepChange(POC_STEP - 1, POC_STEP)).toBe("poc");
  });

  it("switches straight to poc when a jump skips past several steps at once", () => {
    // chat-driven progress can move more than one step between refreshes
    expect(nextTabForStepChange(BPMN_VISUAL_STEP, POC_STEP + 1)).toBe("poc");
  });

  it("does not re-trigger poc once already at/past the PoC step", () => {
    expect(nextTabForStepChange(POC_STEP, POC_STEP + 1)).toBeNull();
  });
});

// A customer reviewer reopened Gate 2 from the PoC tab and was left looking at a locked
// card: the tab did not follow, and the views no longer said what the chat did.

describe("tabWhenPocLocks", () => {
  const GATE_2_STEP = POC_STEP - 1;

  it("leaves the locked PoC tab for the diagram when Gate 2 is reopened", () => {
    expect(tabWhenPocLocks("poc", GATE_2_STEP, true)).toBe("flow");
  });

  it("goes to the blueprint when the session has no diagram", () => {
    expect(tabWhenPocLocks("poc", GATE_2_STEP, false)).toBe("json");
  });

  it("keeps the Blueprint and Workflow tabs where the user left them", () => {
    expect(tabWhenPocLocks("json", GATE_2_STEP, true)).toBeNull();
    expect(tabWhenPocLocks("flow", GATE_2_STEP, true)).toBeNull();
  });

  it("never sends the user from the PoC tab to itself", () => {
    // The PoC tab does not lock from the PoC step on; asked anyway, there is nowhere else to go.
    expect(tabWhenPocLocks("poc", POC_STEP, true)).toBeNull();
    expect(tabWhenPocLocks("poc", POC_STEP + 1, true)).toBeNull();
  });
});
