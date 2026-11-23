import { describe, expect, it } from "vitest";
import {
  DEFAULT_THROTTLE,
  FailureCounter,
  accountKey,
  clientAddress,
  throttleConfig,
} from "./login-throttle";

const env = (vars: Record<string, string>) => vars as unknown as NodeJS.ProcessEnv;
const config = { maxFailures: 3, windowMs: 60_000, lockoutMs: 120_000 };
const T0 = 1_000_000;

describe("FailureCounter", () => {
  it("does not block under the limit", () => {
    const c = new FailureCounter(config);
    c.recordFailure("k", T0);
    c.recordFailure("k", T0 + 1);
    expect(c.isBlocked("k", T0 + 2)).toBe(false);
  });

  it("blocks at the limit, for the lockout", () => {
    const c = new FailureCounter(config);
    for (let i = 0; i < 3; i++) c.recordFailure("k", T0 + i);
    expect(c.isBlocked("k", T0 + 3)).toBe(true);
    expect(c.isBlocked("k", T0 + 2 + 119_999)).toBe(true);
    expect(c.isBlocked("k", T0 + 2 + 120_000)).toBe(false);
  });

  it("forgets failures older than the window", () => {
    const c = new FailureCounter(config);
    c.recordFailure("k", T0);
    c.recordFailure("k", T0 + 1);
    // The first two fall out of the window before the third arrives.
    c.recordFailure("k", T0 + 60_001);
    expect(c.isBlocked("k", T0 + 60_002)).toBe(false);
    expect(c.size).toBe(1);
    expect(c.isBlocked("k", T0 + 200_000)).toBe(false);
    expect(c.size).toBe(0);
  });

  it("keeps keys apart", () => {
    const c = new FailureCounter(config);
    for (let i = 0; i < 3; i++) c.recordFailure("a", T0 + i);
    expect(c.isBlocked("a", T0 + 3)).toBe(true);
    expect(c.isBlocked("b", T0 + 3)).toBe(false);
  });

  it("reset clears the failures of one key", () => {
    const c = new FailureCounter(config);
    c.recordFailure("k", T0);
    c.recordFailure("k", T0 + 1);
    c.reset("k");
    c.recordFailure("k", T0 + 2);
    expect(c.isBlocked("k", T0 + 3)).toBe(false);
  });
});

describe("throttleConfig", () => {
  it("defaults to 5 failures per 10 minutes", () => {
    expect(throttleConfig(env({}))).toEqual(DEFAULT_THROTTLE);
    expect(DEFAULT_THROTTLE).toEqual({ maxFailures: 5, windowMs: 600_000, lockoutMs: 600_000 });
  });

  it("reads the env vars", () => {
    expect(
      throttleConfig(
        env({
          WIZARD_DEV_LOGIN_MAX_FAILURES: "3",
          WIZARD_DEV_LOGIN_WINDOW_S: "60",
          WIZARD_DEV_LOGIN_LOCKOUT_S: "900",
        }),
      ),
    ).toEqual({ maxFailures: 3, windowMs: 60_000, lockoutMs: 900_000 });
  });

  it("falls back to the default for a value that is not a positive integer", () => {
    expect(
      throttleConfig(
        env({ WIZARD_DEV_LOGIN_MAX_FAILURES: "0", WIZARD_DEV_LOGIN_WINDOW_S: "abc" }),
      ),
    ).toEqual(DEFAULT_THROTTLE);
  });
});

describe("clientAddress", () => {
  it("ignores the header when no proxy is configured", () => {
    expect(clientAddress("203.0.113.7", env({}))).toBeNull();
    expect(clientAddress("203.0.113.7", env({ WIZARD_TRUSTED_PROXY_HOPS: "0" }))).toBeNull();
  });

  it("takes the entry the trusted proxy appended, not one the client wrote", () => {
    const one = env({ WIZARD_TRUSTED_PROXY_HOPS: "1" });
    expect(clientAddress("203.0.113.7", one)).toBe("203.0.113.7");
    expect(clientAddress("198.51.100.1, 203.0.113.7", one)).toBe("203.0.113.7");
    const two = env({ WIZARD_TRUSTED_PROXY_HOPS: "2" });
    expect(clientAddress("198.51.100.1, 203.0.113.7, 10.0.0.2", two)).toBe("203.0.113.7");
  });

  it("is null when the header is missing or shorter than the proxy chain", () => {
    const two = env({ WIZARD_TRUSTED_PROXY_HOPS: "2" });
    expect(clientAddress(null, two)).toBeNull();
    expect(clientAddress("203.0.113.7", two)).toBeNull();
  });
});

describe("accountKey", () => {
  it("does not let a change of case start a new count", () => {
    expect(accountKey(" Someone@Example.test ")).toBe(accountKey("someone@example.test"));
  });

  it("keeps a refused key when made-up keys fill the counter", () => {
    const roomy = new FailureCounter({ maxFailures: 5, windowMs: 60_000, lockoutMs: 60_000 });
    for (let i = 0; i < 5; i++) roomy.recordFailure("target", 0);
    for (let i = 0; i < 10_050; i++) roomy.recordFailure(`made-up-${i}`, 1);
    expect(roomy.isBlocked("target", 2)).toBe(true);
    expect(roomy.size).toBeLessThanOrEqual(10_000);
  });
});
