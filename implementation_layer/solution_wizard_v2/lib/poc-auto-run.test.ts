import { describe, expect, it } from "vitest";
import { autoRunDecision, userInputs, type AutoRunInput } from "./poc-auto-run";

const READY: AutoRunInput = {
  onPocTab: true,
  gateApproved: true,
  wizardReplying: false,
  packageStatus: "ready",
  version: "v1",
  hasInput: true,
  busy: false,
  ranVersion: null,
  hasEarlierRun: false,
};

describe("the test run that starts by itself", () => {
  it("starts when the package is checked and the test material is there", () => {
    expect(autoRunDecision(READY)).toBe("run");
  });

  it("waits for the package's check, and where no check can say it is ready", () => {
    for (const packageStatus of ["loading", "missing", "incomplete", "checking", "failed", "unfinished", "unchecked"] as const) {
      expect(autoRunDecision({ ...READY, packageStatus })).toBe("wait");
    }
    // The mock store and an older api give no version: nothing to start a run per.
    expect(autoRunDecision({ ...READY, version: null })).toBe("wait");
  });

  it("waits while the wizard is replying: it may still be writing the package", () => {
    expect(autoRunDecision({ ...READY, wizardReplying: true })).toBe("wait");
  });

  it("waits for Gate 2, the PoC tab, test material, and a run or generation to end", () => {
    expect(autoRunDecision({ ...READY, gateApproved: false })).toBe("wait");
    expect(autoRunDecision({ ...READY, onPocTab: false })).toBe("wait");
    expect(autoRunDecision({ ...READY, hasInput: false })).toBe("wait");
    expect(autoRunDecision({ ...READY, busy: true })).toBe("wait");
  });

  it("waits after a gate was reopened until the wizard has changed the package", () => {
    expect(autoRunDecision({ ...READY, heldVersion: "v1" })).toBe("wait");
    expect(autoRunDecision({ ...READY, version: "v2", heldVersion: "v1" })).toBe("run");
    expect(autoRunDecision({ ...READY, heldVersion: null })).toBe("run");
  });

  it("runs once per package version", () => {
    expect(autoRunDecision({ ...READY, ranVersion: "v1", hasEarlierRun: true })).toBe("wait");
    // The wizard fixed the package after the user's feedback: the new one is run.
    expect(autoRunDecision({ ...READY, version: "v2", ranVersion: "v1", hasEarlierRun: true })).toBe("run");
  });

  it("takes a run from before the page was loaded as its package's", () => {
    expect(autoRunDecision({ ...READY, hasEarlierRun: true })).toBe("adopt");
    // Also without test material in view: the run that happened needed none from here.
    expect(autoRunDecision({ ...READY, hasEarlierRun: true, hasInput: false })).toBe("adopt");
  });
});

describe("the test material the run starts by itself on", () => {
  it("is the user's own files, not the wizard's examples", () => {
    const files = [
      { name: "delivery_note_sample.txt", bytes: 7, uploaded: false },
      { name: "lahete.pdf", bytes: 9, uploaded: true },
    ];
    expect(userInputs(files).map((f) => f.name)).toEqual(["lahete.pdf"]);
    // Only the wizard's examples: nothing to start on, so the tab asks for material.
    expect(userInputs(files.slice(0, 1))).toEqual([]);
  });

  it("counts every file as the user's where the listing does not say (the mock, an older api)", () => {
    expect(userInputs([{ name: "a.pdf", bytes: 1 }])).toHaveLength(1);
  });
});
