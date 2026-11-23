import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const loggerMock = vi.hoisted(() => ({ warn: vi.fn() }));
vi.mock("@/lib/logger", () => ({ logger: loggerMock }));

import { actorId, resetActorIdWarningForTests } from "@/lib/actor-id";

const EMAIL = "Alice.Example@Example.test";

beforeEach(() => {
  vi.stubEnv("WIZARD_PSEUDONYM_KEY", "key-one");
  vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "");
  loggerMock.warn.mockClear();
  resetActorIdWarningForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("actorId", () => {
  it("gives the same person the same id, whatever the case or spacing of the address", () => {
    expect(actorId(EMAIL)).toBe(actorId("  alice.example@example.test "));
  });

  it("gives different people different ids", () => {
    expect(actorId(EMAIL)).not.toBe(actorId("bob@example.test"));
  });

  it("is short, prefixed and hex, and never contains the address", () => {
    const id = actorId(EMAIL);
    expect(id).toMatch(/^u_[0-9a-f]{16}$/);
    expect(id.toLowerCase()).not.toContain("alice");
    expect(id.toLowerCase()).not.toContain("example");
  });

  it("changes with the key, so one deployment's ids say nothing about another's", () => {
    const one = actorId(EMAIL);
    vi.stubEnv("WIZARD_PSEUDONYM_KEY", "key-two");
    expect(actorId(EMAIL)).not.toBe(one);
  });

  it("falls back to the Server Actions key when no pseudonym key is set", () => {
    vi.stubEnv("WIZARD_PSEUDONYM_KEY", "");
    vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "actions-key");
    const id = actorId(EMAIL);
    expect(id).toMatch(/^u_[0-9a-f]{16}$/);
    expect(loggerMock.warn).not.toHaveBeenCalled();
    vi.stubEnv("WIZARD_PSEUDONYM_KEY", "key-one");
    expect(actorId(EMAIL)).not.toBe(id);
  });

  it("without any key still gives a stable id and warns once", () => {
    vi.stubEnv("WIZARD_PSEUDONYM_KEY", "");
    vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "");
    const first = actorId(EMAIL);
    const second = actorId(EMAIL);
    actorId("bob@example.test");
    expect(first).toBe(second);
    expect(first).toMatch(/^u_[0-9a-f]{16}$/);
    expect(loggerMock.warn).toHaveBeenCalledTimes(1);
    expect(String(loggerMock.warn.mock.calls[0][0])).toContain("WIZARD_PSEUDONYM_KEY");
  });
});
