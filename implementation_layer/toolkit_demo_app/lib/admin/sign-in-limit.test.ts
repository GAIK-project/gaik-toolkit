import { afterEach, describe, expect, test } from "bun:test";
import {
  MemoryWindows,
  getSignInLimits,
  takeAdminSignInAttempt,
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
