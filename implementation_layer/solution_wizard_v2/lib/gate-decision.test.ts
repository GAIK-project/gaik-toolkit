import { describe, expect, it } from "vitest";

import {
  decisionGateStep,
  gateDecidableFrom,
  stageGateStep,
  workspaceStep,
  type DecisionSession,
} from "@/lib/gate-decision";
import { GATE_APPROVED_WAKE_TEMPLATES } from "@/lib/chat-reference";
import { GATE_STEPS, buildGateStatus } from "@/lib/wizard-state-machine";

const wake = (gate: number) => ({
  role: "user",
  content: GATE_APPROVED_WAKE_TEMPLATES[0].replace("{n}", String(gate)),
});
const reply = { role: "assistant", content: "Dokumentaatio on päivitetty." };

function session(step: number, over: Partial<DecisionSession> = {}): DecisionSession {
  return { step, gateStatus: buildGateStatus(step), messages: [], ...over };
}

describe("decisionGateStep", () => {
  it("is the gate the session stands on, until it is approved", () => {
    for (const step of GATE_STEPS) {
      expect(decisionGateStep(session(step))).toBe(step);
      expect(decisionGateStep(session(step, { gateStatus: { ...buildGateStatus(step), [step]: "rejected" } }))).toBe(
        step,
      );
      expect(
        decisionGateStep(session(step, { gateStatus: { ...buildGateStatus(step), [step]: "approved" } })),
      ).toBeUndefined();
    }
  });

  it("offers no decision on the steps the wizard works through", () => {
    for (const step of [1, 2, 3, 5, 6, 7, 8]) {
      expect(decisionGateStep(session(step, { lastSuccessfulRun: "run-1", messages: [wake(3), reply] }))).toBeUndefined();
    }
  });

  it("offers Gate 1 from the steps before it once the wizard has recorded what it reviews", () => {
    const context = { currentProcess: "Invoices are typed in by hand." };
    for (const step of [1, 2, 3]) {
      expect(decisionGateStep(session(step, { businessContext: null, assumptions: [] }))).toBeUndefined();
      expect(decisionGateStep(session(step, { businessContext: context }))).toBe(4);
      expect(decisionGateStep(session(step, { assumptions: [{ id: "a1" }] }))).toBe(4);
      // An approval given before the step back still stands.
      expect(
        decisionGateStep(session(step, { businessContext: context, gateStatus: { ...buildGateStatus(step), 4: "approved" } })),
      ).toBeUndefined();
    }
    // Past Gate 1 the recorded context offers nothing by itself.
    expect(decisionGateStep(session(6, { businessContext: context }))).toBeUndefined();
  });

  it("offers Gate 3 from the PoC step once a test run has succeeded", () => {
    expect(decisionGateStep(session(10))).toBeUndefined();
    expect(decisionGateStep(session(10, { lastSuccessfulRun: null }))).toBeUndefined();
    expect(decisionGateStep(session(10, { lastSuccessfulRun: "run-1" }))).toBe(11);
  });

  it("offers Gate 4 from the documentation step once the wizard has replied to Gate 3's approval", () => {
    // Just approved: the wizard has not answered yet.
    expect(decisionGateStep(session(12, { messages: [reply, wake(3)] }))).toBeUndefined();
    expect(decisionGateStep(session(12, { messages: [reply] }))).toBeUndefined();
    expect(decisionGateStep(session(12, { messages: [wake(3), reply] }))).toBe(13);
    // A later exchange keeps it, as long as the wizard has the last word.
    const later = [wake(3), reply, { role: "user", content: "Lisää vielä ohje." }];
    expect(decisionGateStep(session(12, { messages: later }))).toBeUndefined();
    expect(decisionGateStep(session(12, { messages: [...later, reply] }))).toBe(13);
    // Not while it is replying, and not for another gate's approval.
    expect(
      decisionGateStep(session(12, { messages: [wake(3), reply], pendingTurn: { userMessage: "x" } })),
    ).toBeUndefined();
    expect(decisionGateStep(session(12, { messages: [wake(2), reply] }))).toBeUndefined();
  });

  it("offers Gate 2 through its stage once the wizard's files reach the diagram and it has replied to Gate 1's approval", () => {
    const ready = { reachedStep: 9, messages: [wake(1), reply] };
    for (const step of [5, 6, 7, 8]) {
      expect(decisionGateStep(session(step, ready))).toBe(9);
      // The files are not there yet, or the store does not say (the mock).
      expect(decisionGateStep(session(step, { ...ready, reachedStep: 7 }))).toBeUndefined();
      expect(decisionGateStep(session(step, { messages: ready.messages }))).toBeUndefined();
      // Gate 1 was approved a moment ago and the wizard has not answered, or is answering.
      expect(decisionGateStep(session(step, { reachedStep: 9, messages: [reply, wake(1)] }))).toBeUndefined();
      expect(decisionGateStep(session(step, { ...ready, pendingTurn: { userMessage: "x" } }))).toBeUndefined();
    }
  });

  it("on a gate that is already approved offers the next gate, once that one is ready", () => {
    const approved = (step: number) => ({ ...buildGateStatus(step), [step]: "approved" as const });
    expect(decisionGateStep(session(9, { gateStatus: approved(9) }))).toBeUndefined();
    expect(decisionGateStep(session(9, { gateStatus: approved(9), lastSuccessfulRun: "run-1" }))).toBe(11);
    expect(decisionGateStep(session(11, { gateStatus: approved(11), messages: [wake(3), reply] }))).toBe(13);
    expect(
      decisionGateStep(session(4, { gateStatus: approved(4), reachedStep: 10, messages: [wake(1), reply] })),
    ).toBe(9);
    // The last gate has nothing after it.
    expect(decisionGateStep(session(13, { gateStatus: approved(13), lastSuccessfulRun: "run-1" }))).toBeUndefined();
  });
});

describe("stageGateStep", () => {
  it("is the first gate at or after the step that is not approved", () => {
    expect([1, 4, 5, 8, 9, 10, 11, 12, 13].map((step) => stageGateStep(session(step)))).toEqual([
      4, 4, 9, 9, 9, 11, 11, 13, 13,
    ]);
    expect(stageGateStep(session(9, { gateStatus: { ...buildGateStatus(9), 9: "approved" } }))).toBe(11);
    expect(stageGateStep(session(13, { gateStatus: { ...buildGateStatus(13), 13: "approved" } }))).toBeUndefined();
  });
});

describe("workspaceStep", () => {
  it("follows the wizard's files within the stage, never past the gate that waits", () => {
    expect(workspaceStep(session(5))).toBe(5);
    expect(workspaceStep(session(5, { reachedStep: 7 }))).toBe(7);
    expect(workspaceStep(session(5, { reachedStep: 9 }))).toBe(9);
    // The package of an earlier round is on disk: Gate 2 still waits.
    expect(workspaceStep(session(5, { reachedStep: 10 }))).toBe(9);
    expect(workspaceStep(session(10, { reachedStep: 9 }))).toBe(10);
    const done = { ...buildGateStatus(13), 13: "approved" as const };
    expect(workspaceStep(session(13, { gateStatus: done, reachedStep: 10 }))).toBe(13);
  });
});

describe("gateDecidableFrom", () => {
  it("takes a decision on the gate itself until it is approved", () => {
    for (const step of GATE_STEPS) {
      expect(gateDecidableFrom(session(step), step)).toBe(true);
      expect(gateDecidableFrom(session(step, { gateStatus: { ...buildGateStatus(step), [step]: "approved" } }), step)).toBe(
        false,
      );
    }
  });

  it("takes a gate from any step of its stage", () => {
    expect(gateDecidableFrom(session(10), 11)).toBe(true);
    expect(gateDecidableFrom(session(12), 13)).toBe(true);
    for (const step of [1, 2, 3]) expect(gateDecidableFrom(session(step), 4)).toBe(true);
    for (const step of [5, 6, 7, 8]) expect(gateDecidableFrom(session(step), 9)).toBe(true);
    expect(gateDecidableFrom(session(2, { gateStatus: { ...buildGateStatus(2), 4: "approved" } }), 4)).toBe(false);
    // From the gate before, once that one is approved.
    expect(gateDecidableFrom(session(9), 11)).toBe(false);
    expect(gateDecidableFrom(session(9, { gateStatus: { ...buildGateStatus(9), 9: "approved" } }), 11)).toBe(true);
  });

  it("does not depend on whether the wizard is replying: that is wizard_api's answer to give", () => {
    const replying = session(12, { pendingTurn: { userMessage: "x" }, messages: [{ role: "user", content: "x" }] });
    expect(decisionGateStep(replying)).toBeUndefined();
    expect(gateDecidableFrom(replying, 13)).toBe(true);
  });

  it("refuses a gate the session has passed, one further ahead, and a step that is no gate", () => {
    expect(gateDecidableFrom(session(12), 11)).toBe(false);
    expect(gateDecidableFrom(session(10), 13)).toBe(false);
    expect(gateDecidableFrom(session(10), 12)).toBe(false);
    expect(gateDecidableFrom(session(11), Number.NaN)).toBe(false);
  });
});
