import { describe, expect, it } from "vitest";
import {
  BPMN_SPIKE_SESSION_IDS,
  BPMN_V2_STARTED,
  BPMN_VISUAL_STEP,
  CHAT_COLLAPSE_FROM_STEP,
  hasBpmnSpike,
  shouldCollapseChatByDefault,
  shouldShowBpmnSpike,
} from "@/lib/bpmn-spike";

describe("bpmn-spike", () => {
  it("marks V2 BPMN as started", () => {
    expect(BPMN_V2_STARTED).toBe(true);
  });

  it("enables mock seed session ids", () => {
    expect(hasBpmnSpike("ses_chatbot")).toBe(true);
    expect(BPMN_SPIKE_SESSION_IDS.has("ses_laskut")).toBe(true);
  });

  it("enables UUID sessions from wizard_api", () => {
    expect(hasBpmnSpike("550e8400-e29b-41d4-a716-446655440000")).toBe(true);
  });

  it("enables newly created mock sessions (ses_ + short hex)", () => {
    expect(hasBpmnSpike("ses_a1b2c3d4")).toBe(true);
  });

  it("rejects unknown short ids", () => {
    expect(hasBpmnSpike("ses_unknown")).toBe(false);
  });

  it("requires phase 8+ for BPMN display", () => {
    expect(shouldShowBpmnSpike("ses_chatbot", BPMN_VISUAL_STEP - 1)).toBe(false);
    expect(shouldShowBpmnSpike("ses_chatbot", BPMN_VISUAL_STEP)).toBe(true);
    expect(
      shouldShowBpmnSpike(
        "550e8400-e29b-41d4-a716-446655440000",
        BPMN_VISUAL_STEP,
      ),
    ).toBe(true);
    expect(shouldShowBpmnSpike("ses_a1b2c3d4", BPMN_VISUAL_STEP)).toBe(true);
  });

  it("collapses chat by default from the BPMN visual step", () => {
    expect(CHAT_COLLAPSE_FROM_STEP).toBe(BPMN_VISUAL_STEP);
    expect(shouldCollapseChatByDefault(BPMN_VISUAL_STEP - 1)).toBe(false);
    expect(shouldCollapseChatByDefault(BPMN_VISUAL_STEP)).toBe(true);
  });

  it("keeps the chat open while a gate waits for approval", () => {
    // Gate 2 (step 9) and Gate 3 (step 11) pending: the agent's summary sits
    // in the chat beside the decision bar.
    expect(shouldCollapseChatByDefault(9, true)).toBe(false);
    expect(shouldCollapseChatByDefault(11, true)).toBe(false);
    // Once approved the session is past the gate, and the workspace leads again.
    expect(shouldCollapseChatByDefault(10, false)).toBe(true);
  });
});
