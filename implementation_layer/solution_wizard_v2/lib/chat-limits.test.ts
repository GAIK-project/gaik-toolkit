import { describe, expect, it } from "vitest";
import { MAX_CHAT_MESSAGE_CHARS, chatMessageTooLong, chatRefusalLabel } from "./chat-limits";

describe("chat message limit", () => {
  it("accepts a message up to the limit", () => {
    expect(chatMessageTooLong("x".repeat(MAX_CHAT_MESSAGE_CHARS))).toBe(false);
  });

  it("refuses a longer one", () => {
    expect(chatMessageTooLong("x".repeat(MAX_CHAT_MESSAGE_CHARS + 1))).toBe(true);
  });
});

describe("chat refusal message", () => {
  const labels = {
    tooLong: "too long",
    capacity: "capacity",
    agentBusy: "agent busy",
    rateLimited: "rate limited",
    turnLimit: "turn limit",
    usageSession: "session cap",
    usageUser: "user cap",
    usageDeployment: "deployment cap",
  };

  it("says the user's own agents are busy for a 429 agent_busy", () => {
    expect(chatRefusalLabel(429, "agent_busy", labels)).toBe("agent busy");
  });

  it("says the user is sending too fast for a 429 rate_limited", () => {
    expect(chatRefusalLabel(429, "rate_limited", labels)).toBe("rate limited");
  });

  it("treats a 429 without a code as agent_busy", () => {
    expect(chatRefusalLabel(429, undefined, labels)).toBe("agent busy");
  });

  it("keeps the existing 413 and 503 messages and leaves other answers alone", () => {
    expect(chatRefusalLabel(413, undefined, labels)).toBe("too long");
    expect(chatRefusalLabel(503, undefined, labels)).toBe("capacity");
    expect(chatRefusalLabel(200, undefined, labels)).toBeUndefined();
    expect(chatRefusalLabel(429, "agent_busy", undefined)).toBeUndefined();
  });

  it("names whose usage cap a 402 reached, the session's when the scope is unknown", () => {
    expect(chatRefusalLabel(402, "usage_cap", labels, "session")).toBe("session cap");
    expect(chatRefusalLabel(402, "usage_cap", labels, "user")).toBe("user cap");
    expect(chatRefusalLabel(402, "usage_cap", labels, "deployment")).toBe("deployment cap");
    expect(chatRefusalLabel(402, "usage_cap", labels, "something")).toBe("session cap");
  });
});
