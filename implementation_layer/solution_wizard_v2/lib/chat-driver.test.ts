import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Dict } from "@/lib/i18n";
import type { WizardSession } from "@/lib/mock-sessions";

const sessionsMock = vi.hoisted(() => ({ recordRequirementAnswer: vi.fn() }));
vi.mock("@/lib/sessions", () => sessionsMock);

import { resolveChatReply, toStreamTokens } from "@/lib/chat-driver";
import { REQUIREMENT_POINTS } from "@/lib/requirements-model";

const t = {
  phases: ["Session start", "Requirements gathering", "Specification", "Gate 1"],
  chatMockReplyPre: "Thanks for your message. I've logged it under step ",
  chatMockReplyPost: ". (Mock reply.)",
} as unknown as Dict;

function session(overrides: Partial<WizardSession> = {}): WizardSession {
  return {
    id: "s1",
    step: 1,
    requirements: { points: REQUIREMENT_POINTS, answers: [] },
    ...overrides,
  } as WizardSession;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("resolveChatReply", () => {
  it("records the answer and asks the next question while gathering (step <= 3)", async () => {
    sessionsMock.recordRequirementAnswer.mockResolvedValue(undefined);
    const reply = await resolveChatReply("s1", session({ step: 2 }), "our answer", t);
    expect(sessionsMock.recordRequirementAnswer).toHaveBeenCalledWith("s1", "our answer");
    expect(reply).toContain(REQUIREMENT_POINTS[1]);
  });

  it("wraps up once every requirement point has been answered", async () => {
    const allAnswered = session({
      step: 3,
      requirements: { points: REQUIREMENT_POINTS, answers: REQUIREMENT_POINTS.slice(0, -1) },
    });
    const reply = await resolveChatReply("s1", allAnswered, "last answer", t);
    expect(reply).toMatch(/Gate 1/);
  });

  it("falls back to the phase-aware mock reply once gathering is done (step > 3)", async () => {
    const reply = await resolveChatReply("s1", session({ step: 4 }), "anything", t);
    expect(sessionsMock.recordRequirementAnswer).not.toHaveBeenCalled();
    expect(reply).toBe('Thanks for your message. I\'ve logged it under step "Gate 1". (Mock reply.)');
  });

  it("falls back to the mock reply when the session has no requirements object", async () => {
    const reply = await resolveChatReply("s1", session({ step: 1, requirements: undefined }), "x", t);
    expect(sessionsMock.recordRequirementAnswer).not.toHaveBeenCalled();
    expect(reply).toContain("Session start");
  });
});

describe("toStreamTokens", () => {
  it("splits a reply into word tokens that retain trailing whitespace", () => {
    expect(toStreamTokens("Hello there, world")).toEqual(["Hello ", "there, ", "world"]);
  });

  it("returns the whole string as a single token when there's no whitespace match", () => {
    expect(toStreamTokens("")).toEqual([""]);
  });
});
