import { afterEach, describe, expect, it, vi } from "vitest";
import { DEV_SESSION_MAX_AGE_S, signDevSession, verifyDevSession } from "./dev-session";

const NOW = Date.parse("2026-10-03T12:00:00Z");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("signed dev session (P5)", () => {
  it("verifies what it signed, for a dev account", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "test-secret");
    const cookie = await signDevSession("dev@gaik.local", NOW);
    expect(cookie.split("|")).toHaveLength(3);
    expect(await verifyDevSession(cookie, NOW)).toBe("dev@gaik.local");
  });

  it("rejects the old bare-email format — the value an attacker would type", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "test-secret");
    expect(await verifyDevSession("dev@gaik.local", NOW)).toBeNull();
    expect(await verifyDevSession(undefined, NOW)).toBeNull();
    expect(await verifyDevSession("", NOW)).toBeNull();
  });

  it("rejects a tampered email, expiry or signature", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "test-secret");
    const cookie = await signDevSession("dev@gaik.local", NOW);
    const [email, expires, signature] = cookie.split("|");
    expect(await verifyDevSession(`dev2@gaik.local|${expires}|${signature}`, NOW)).toBeNull();
    expect(await verifyDevSession(`${email}|${Number(expires) + 3600}|${signature}`, NOW)).toBeNull();
    expect(await verifyDevSession(`${email}|${expires}|${signature.slice(0, -1)}A`, NOW)).toBeNull();
  });

  it("rejects a signature made with another secret", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "secret-of-another-instance");
    const cookie = await signDevSession("dev@gaik.local", NOW);
    vi.stubEnv("DEV_AUTH_SECRET", "this-instance");
    expect(await verifyDevSession(cookie, NOW)).toBeNull();
  });

  it("expires", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "test-secret");
    const cookie = await signDevSession("dev@gaik.local", NOW);
    expect(await verifyDevSession(cookie, NOW + (DEV_SESSION_MAX_AGE_S - 1) * 1000)).toBe("dev@gaik.local");
    expect(await verifyDevSession(cookie, NOW + DEV_SESSION_MAX_AGE_S * 1000)).toBeNull();
  });

  it("does not sign a session for an account that is not a dev account", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "test-secret");
    const cookie = await signDevSession("someone@example.com", NOW);
    expect(await verifyDevSession(cookie, NOW)).toBeNull();
  });

  it("falls back to the Server Actions key, and warns when there is no key at all", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "");
    vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "actions-key");
    const signedWithActionsKey = await signDevSession("dev@gaik.local", NOW);
    expect(await verifyDevSession(signedWithActionsKey, NOW)).toBe("dev@gaik.local");

    vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const unsigned = await signDevSession("dev@gaik.local", NOW);
    expect(await verifyDevSession(signedWithActionsKey, NOW)).toBeNull();
    expect(await verifyDevSession(unsigned, NOW)).toBe("dev@gaik.local");
    expect(warn.mock.calls.some((c) => String(c[0]).includes("can be forged"))).toBe(true);
  });

  it("has no fallback key on a production build: nothing verifies and nothing is signed", async () => {
    vi.stubEnv("DEV_AUTH_SECRET", "test-secret");
    const signedEarlier = await signDevSession("dev@gaik.local", NOW);

    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DEV_AUTH_SECRET", "");
    vi.stubEnv("NEXT_SERVER_ACTIONS_ENCRYPTION_KEY", "");
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await verifyDevSession(signedEarlier, NOW)).toBeNull();
    await expect(signDevSession("dev@gaik.local", NOW)).rejects.toThrow(/disabled/);
  });
});
