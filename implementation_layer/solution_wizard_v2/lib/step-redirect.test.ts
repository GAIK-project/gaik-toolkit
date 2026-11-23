import { describe, expect, it } from "vitest";
import { afterStepAction, withoutStepParams } from "./step-redirect";

describe("withoutStepParams", () => {
  it("drops the wake-up and the notice and keeps the open tab", () => {
    expect(withoutStepParams("/sessions/s1", "?wake=2")).toBe("/sessions/s1");
    expect(withoutStepParams("/sessions/s1", "?tab=poc&wake=2&notice=agent_busy")).toBe("/sessions/s1?tab=poc");
    expect(withoutStepParams("/sessions/s1", "")).toBe("/sessions/s1");
  });

  it("sets a new notice in place of the old one", () => {
    expect(withoutStepParams("/sessions/s1", "?tab=poc&notice=agent_busy", "gate_moved")).toBe(
      "/sessions/s1?tab=poc&notice=gate_moved",
    );
  });
});

describe("afterStepAction", () => {
  it("shows a refusal as a notice", () => {
    expect(afterStepAction("s1", { notice: "agent_busy" })).toBe("/sessions/s1?notice=agent_busy");
    expect(afterStepAction("s1", { notice: "gate_not_ready", hadNotice: true })).toBe(
      "/sessions/s1?notice=gate_not_ready",
    );
  });

  it("drops an earlier notice once the step change goes through", () => {
    expect(afterStepAction("s1", { hadNotice: true })).toBe("/sessions/s1");
  });

  it("wakes the agent after a gate approval, notice or not", () => {
    expect(afterStepAction("s1", { wake: 3 })).toBe("/sessions/s1?wake=3");
    expect(afterStepAction("s1", { wake: 4, hadNotice: true })).toBe("/sessions/s1?wake=4");
  });

  it("stays on the page when there is nothing to show or clear", () => {
    expect(afterStepAction("s1", {})).toBeNull();
    expect(afterStepAction("s1", { notice: null, hadNotice: false })).toBeNull();
  });
});
