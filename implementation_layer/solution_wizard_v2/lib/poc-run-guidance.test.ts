import { describe, expect, it } from "vitest";
import { pocActionEmphasis } from "@/lib/poc-run-guidance";

const base = {
  pocGenerated: true,
  pocReady: true,
  checkFailed: false,
  runPhase: "idle",
  autoRunDecision: "wait" as const,
  autoRunNeedsInput: false,
  autoRunComing: false,
  autoRunWaiting: false,
  inputBusy: false,
  pocInputs: [],
  ownInputs: [],
};

describe("pocActionEmphasis", () => {
  it("makes uploading the sole primary action when a ready package needs input", () => {
    const res = pocActionEmphasis({
      ...base,
      autoRunNeedsInput: true,
    });
    expect(res.uploadPrimary).toBe(true);
    expect(res.runPrimary).toBe(false);
  });

  it("names ready sample files while still prioritizing adding the user's test file", () => {
    const res = pocActionEmphasis({
      ...base,
      autoRunNeedsInput: true,
      pocInputs: [{ name: "sample_call.wav", bytes: 4096, uploaded: false }],
    });
    expect(res.uploadPrimary).toBe(true);
    expect(res.runPrimary).toBe(false);
    expect(res.sampleNames).toEqual(["sample_call.wav"]);
  });

  it("marks the run queued when auto-run is about to start and avoids two primary buttons", () => {
    const res = pocActionEmphasis({
      ...base,
      autoRunDecision: "run",
      autoRunComing: true,
      pocInputs: [{ name: "fault.wav", bytes: 4096, uploaded: true }],
      ownInputs: [{ name: "fault.wav", bytes: 4096, uploaded: true }],
    });
    expect(res.uploadPrimary).toBe(false);
    expect(res.runPrimary).toBe(false);
    expect(res.runQueued).toBe(true);
    expect(res.ownNames).toEqual(["fault.wav"]);
  });

  it("gives the manual run button primary emphasis after a failed run with input present", () => {
    const res = pocActionEmphasis({
      ...base,
      runPhase: "failed",
      pocInputs: [{ name: "fault.wav", bytes: 4096, uploaded: true }],
      ownInputs: [{ name: "fault.wav", bytes: 4096, uploaded: true }],
    });
    expect(res.uploadPrimary).toBe(false);
    expect(res.runPrimary).toBe(true);
  });
});
