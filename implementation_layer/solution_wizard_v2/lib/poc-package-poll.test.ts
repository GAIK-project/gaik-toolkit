import { describe, expect, it } from "vitest";
import { READY_POLL_MS, WRITING_POLL_MS, pocPollDelay } from "./poc-package-poll";

// Round 11 (6 Oct 2026): the PoC tab was open while the agent finished the
// package; it kept showing the run disabled until a reload. The open tab must
// keep asking the api for the package, at a pace that fits what it knows.

const base = { onPocTab: true, visible: true, ready: false, runActive: false };

describe("pocPollDelay", () => {
  it("asks often while the package is still being written", () => {
    expect(pocPollDelay(base)).toBe(WRITING_POLL_MS);
  });

  it("keeps asking, less often, once the package is ready (the agent rewrites it)", () => {
    expect(pocPollDelay({ ...base, ready: true })).toBe(READY_POLL_MS);
    expect(READY_POLL_MS).toBeGreaterThan(WRITING_POLL_MS);
  });

  it("does not ask from another tab, a hidden page or during a run", () => {
    expect(pocPollDelay({ ...base, onPocTab: false })).toBeNull();
    expect(pocPollDelay({ ...base, visible: false })).toBeNull();
    expect(pocPollDelay({ ...base, runActive: true })).toBeNull();
  });
});
