import { describe, expect, it } from "vitest";
import {
  apiGateKeyForStep,
  apiGatesToUi,
  uiGateApprovalPatch,
} from "@/lib/session-gate-map";

describe("apiGatesToUi", () => {
  const pending = {
    gate_1: "pending",
    gate_2: "pending",
    gate_3: "pending",
    gate_4: "pending",
  };

  it("locks future gates on step 1", () => {
    const gates = apiGatesToUi(1, pending);
    expect(gates[4]).toBe("locked");
    expect(gates[9]).toBe("locked");
  });

  it("marks passed gates approved on step 8", () => {
    const gates = apiGatesToUi(8, { ...pending, gate_1: "approved" });
    expect(gates[4]).toBe("approved");
    expect(gates[9]).toBe("locked");
  });

  it("shows pending on current gate step", () => {
    const gates = apiGatesToUi(4, pending);
    expect(gates[4]).toBe("pending");
    expect(gates[9]).toBe("locked");
  });

  it("maps rejected at current gate", () => {
    const gates = apiGatesToUi(9, {
      ...pending,
      gate_1: "approved",
      gate_2: "rejected",
    });
    expect(gates[9]).toBe("rejected");
  });
});

describe("apiGateKeyForStep", () => {
  it("maps gate steps to API keys", () => {
    expect(apiGateKeyForStep(4)).toBe("gate_1");
    expect(apiGateKeyForStep(13)).toBe("gate_4");
    expect(apiGateKeyForStep(5)).toBeUndefined();
  });
});

describe("uiGateApprovalPatch", () => {
  it("returns approval patch for gate steps only", () => {
    expect(uiGateApprovalPatch(4)).toEqual({ gate_1: "approved" });
    expect(uiGateApprovalPatch(5)).toBeUndefined();
  });
});

describe("apiGatesToUi after going back", () => {
  const pending = {
    gate_1: "pending",
    gate_2: "pending",
    gate_3: "pending",
    gate_4: "pending",
  };

  it("keeps an approval the user already gave when they step back below it", () => {
    // 22 / R8: going back "cancelled" the Gate 1 approval. The approval was
    // never lost in storage — the map flattened it to "locked" on the way out.
    const gates = apiGatesToUi(2, { ...pending, gate_1: "approved" });

    expect(gates[4]).toBe("approved");
  });

  it("keeps a rejection visible from below too", () => {
    const gates = apiGatesToUi(2, { ...pending, gate_1: "rejected" });

    expect(gates[4]).toBe("rejected");
  });

  it("still locks a gate nobody has ruled on", () => {
    const gates = apiGatesToUi(2, pending);

    expect(gates[4]).toBe("locked");
    expect(gates[9]).toBe("locked");
  });
});
