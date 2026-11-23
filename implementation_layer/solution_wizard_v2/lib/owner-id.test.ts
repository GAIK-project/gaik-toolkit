import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actorId } from "@/lib/actor-id";
import { OWNER_ID_PATTERN, ownerId } from "@/lib/owner-id";

const EMAIL = "Alice.Example@Example.test";
// The same vector is in wizard_api/tests/test_owner_ids.py: the admin commands
// there must give one address the id this app sends.
const VECTOR = "o_f1520e92ff2e1f898cf5595f579d3801";

beforeEach(() => {
  vi.stubEnv("WIZARD_PSEUDONYM_KEY", "key-one");
  vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("ownerId", () => {
  it("matches wizard_api's id for the same address and key", () => {
    expect(ownerId(EMAIL)).toBe(VECTOR);
  });

  it("gives the same person the same id whatever the case or spacing, and others another", () => {
    expect(ownerId("  alice.example@example.test ")).toBe(VECTOR);
    expect(ownerId("bob@example.test")).not.toBe(VECTOR);
  });

  it("holds nothing of the address and differs from the log pseudonym", () => {
    expect(ownerId(EMAIL)).toMatch(OWNER_ID_PATTERN);
    expect(ownerId(EMAIL)).not.toContain("alice");
    expect(ownerId(EMAIL).slice(2)).not.toContain(actorId(EMAIL).slice(2));
  });

  it("changes with the key", () => {
    vi.stubEnv("WIZARD_PSEUDONYM_KEY", "key-two");
    expect(ownerId(EMAIL)).not.toBe(VECTOR);
  });
});
