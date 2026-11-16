import { afterEach, describe, expect, test } from "bun:test";
import { createHmac } from "node:crypto";
import {
  adminPasswordMatches,
  adminSessionId,
  createAdminSessionValue,
  verifyAdminSessionValue,
} from "./session";

const PASSWORD = "sample-admin-password";

afterEach(() => {
  delete process.env.ADMIN_PASSWORD;
  delete process.env.ADMIN_SESSION_SECRET;
});

describe("admin password", () => {
  test("only the configured password matches", () => {
    process.env.ADMIN_PASSWORD = PASSWORD;
    expect(adminPasswordMatches(PASSWORD)).toBe(true);
    expect(adminPasswordMatches(`${PASSWORD} `)).toBe(false);
    expect(adminPasswordMatches("")).toBe(false);
  });

  test("nothing matches when no password is configured", () => {
    expect(adminPasswordMatches("")).toBe(false);
    expect(adminPasswordMatches(PASSWORD)).toBe(false);
  });
});

describe("admin session cookie", () => {
  test("a cookie the server signed verifies and names its session", () => {
    process.env.ADMIN_PASSWORD = PASSWORD;
    const value = createAdminSessionValue();
    expect(value).not.toBeNull();
    expect(verifyAdminSessionValue(value!)).toBe(true);
    expect(adminSessionId(value!)).toBe(value!.split(".")[1].slice(0, 8));
  });

  test("without a session secret the password itself does not sign the cookie", () => {
    process.env.ADMIN_PASSWORD = PASSWORD;
    const payload = `${Date.now() + 60_000}.abcdefgh`;
    const signedWithPassword = `${payload}.${createHmac("sha256", PASSWORD).update(payload).digest("base64url")}`;
    expect(verifyAdminSessionValue(signedWithPassword)).toBe(false);
    expect(adminSessionId(signedWithPassword)).toBeNull();
  });

  test("a cookie signed under another password or secret does not verify", () => {
    process.env.ADMIN_PASSWORD = PASSWORD;
    const value = createAdminSessionValue()!;
    process.env.ADMIN_PASSWORD = "another-password";
    expect(verifyAdminSessionValue(value)).toBe(false);
    process.env.ADMIN_SESSION_SECRET = "a-separate-secret";
    const withSecret = createAdminSessionValue()!;
    expect(verifyAdminSessionValue(withSecret)).toBe(true);
    process.env.ADMIN_SESSION_SECRET = "a-rotated-secret";
    expect(verifyAdminSessionValue(withSecret)).toBe(false);
  });

  test("an expired or unsigned cookie does not verify", () => {
    process.env.ADMIN_SESSION_SECRET = "a-separate-secret";
    expect(verifyAdminSessionValue("authenticated")).toBe(false);
    expect(verifyAdminSessionValue(undefined)).toBe(false);
    const payload = `${Date.now() - 1}.abcdefgh`;
    const expired = `${payload}.${createHmac("sha256", "a-separate-secret").update(payload).digest("base64url")}`;
    expect(verifyAdminSessionValue(expired)).toBe(false);
  });
});
