import { afterEach, describe, expect, test } from "bun:test";
import {
  MemoryWindows,
  type SharedLimit,
  getSignInLimits,
  takeAdminSignInAttempt,
  takeAttempt,
} from "./sign-in-limit";

afterEach(() => {
  delete process.env.ADMIN_SIGN_IN_ATTEMPTS;
  delete process.env.ADMIN_SIGN_IN_ATTEMPTS_TOTAL;
});

describe("MemoryWindows", () => {
  test("a key gets its limit of attempts per window, then none until the next", () => {
    let now = 1_000_000;
    const windows = new MemoryWindows(() => now);
    expect([1, 2, 3].map(() => windows.take("a", 2, 60_000))).toEqual([
      true,
      true,
      false,
    ]);
    expect(windows.take("b", 2, 60_000)).toBe(true);
    now += 60_000;
    expect(windows.take("a", 2, 60_000)).toBe(true);
  });

  test("a full map refuses a new key and keeps every running count", () => {
    let now = 1_000_000;
    const windows = new MemoryWindows(() => now, 2);
    expect(windows.take("total", 2, 3_600_000)).toBe(true);
    expect(windows.take("a", 1, 60_000)).toBe(true);
    expect(windows.take("b", 1, 60_000)).toBe(false); // full: refused, nothing cleared
    expect(windows.take("total", 2, 3_600_000)).toBe(true);
    expect(windows.take("total", 2, 3_600_000)).toBe(false);
    now += 60_000; // "a" has ended and makes room; "total" is still running
    expect(windows.take("b", 1, 60_000)).toBe(true);
    expect(windows.take("total", 2, 3_600_000)).toBe(false);
  });
});

describe("shared counters", () => {
  const limits = { perAddress: 1, total: 100 };
  const timingOut: SharedLimit = async () => ({
    success: true,
    reason: "timeout",
  });

  test("an answer that timed out is counted in memory, so the limit holds", async () => {
    const windows = new MemoryWindows();
    expect(await takeAttempt(timingOut, "203.0.113.5", limits, windows)).toBe(
      true,
    );
    expect(await takeAttempt(timingOut, "203.0.113.5", limits, windows)).toBe(
      false,
    );
  });

  test("an error is counted in memory, and a refusal is final", async () => {
    const windows = new MemoryWindows();
    const failing: SharedLimit = async () => {
      throw new Error("unreachable");
    };
    expect(await takeAttempt(failing, "203.0.113.6", limits, windows)).toBe(
      true,
    );
    expect(await takeAttempt(failing, "203.0.113.6", limits, windows)).toBe(
      false,
    );
    const refusing: SharedLimit = async () => ({ success: false });
    expect(await takeAttempt(refusing, "203.0.113.7", limits, windows)).toBe(
      false,
    );
  });
});

describe("admin sign-in attempts", () => {
  test("defaults allow five attempts per address and thirty in all", () => {
    expect(getSignInLimits()).toEqual({ perAddress: 5, total: 30 });
  });

  test("without Redis an address is refused after its attempts, others are not", async () => {
    process.env.ADMIN_SIGN_IN_ATTEMPTS = "2";
    const results = [];
    for (let i = 0; i < 3; i++)
      results.push(await takeAdminSignInAttempt("192.0.2.10"));
    expect(results).toEqual([true, true, false]);
    expect(await takeAdminSignInAttempt("192.0.2.11")).toBe(true);
  });

  test("without Redis all addresses together share the hourly ceiling", async () => {
    process.env.ADMIN_SIGN_IN_ATTEMPTS_TOTAL = "1";
    // Earlier tests in this file already used the window's attempts.
    expect(await takeAdminSignInAttempt("198.51.100.20")).toBe(false);
  });
});
