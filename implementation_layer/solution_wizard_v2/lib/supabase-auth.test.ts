import { describe, expect, it, vi } from "vitest";
import {
  accessRequestsEnabled,
  devAuthActive,
  hasWizardAccess,
  rowGrantsAccess,
  supabaseAuthEnabled,
  supabaseSettings,
  supabaseSignUpUrl,
} from "@/lib/supabase-auth";

const env = (vars: Record<string, string>) => vars as unknown as NodeJS.ProcessEnv;

/** A Supabase client whose access_requests query returns ``row`` (or ``error``). */
function client(row: unknown, error: unknown = null) {
  const query = {
    select: vi.fn(() => query),
    eq: vi.fn(() => query),
    maybeSingle: vi.fn(async () => ({ data: row, error })),
  };
  return { from: vi.fn(() => query), query };
}

/** The fake client stands in for the one query the check makes. */
const access = (c: unknown, user: Parameters<typeof hasWizardAccess>[1], e: NodeJS.ProcessEnv) =>
  hasWizardAccess(c as never, user, e);

const confirmed = { id: "u1", email: "ada@example.test", email_confirmed_at: "2026-11-20T10:00:00Z" };
const byRows = env({ WIZARD_SUPABASE_ACCESS: "access_requests" });

describe("supabase sign-in settings", () => {
  it("is on only with WIZARD_AUTH_MODE=supabase", () => {
    expect(supabaseAuthEnabled(env({ WIZARD_AUTH_MODE: " supabase " }))).toBe(true);
    expect(supabaseAuthEnabled(env({ WIZARD_AUTH_MODE: "proxy" }))).toBe(false);
    expect(supabaseAuthEnabled(env({}))).toBe(false);
  });

  it("turns the dev login off for an image built with it", () => {
    // DEV_AUTH comes from the build; in the test run it is off, so only the
    // Supabase mode's veto can be seen here.
    expect(devAuthActive(env({ WIZARD_AUTH_MODE: "supabase" }))).toBe(false);
  });

  it("reads the project at run time, before the build-time pair", () => {
    expect(
      supabaseSettings(
        env({
          WIZARD_SUPABASE_URL: "https://run.example.test",
          WIZARD_SUPABASE_KEY: "run-key",
          NEXT_PUBLIC_SUPABASE_URL: "https://build.example.test",
          NEXT_PUBLIC_SUPABASE_ANON_KEY: "build-key",
        }),
      ),
    ).toEqual({ url: "https://run.example.test", key: "run-key" });
    expect(
      supabaseSettings(
        env({ NEXT_PUBLIC_SUPABASE_URL: "https://build.example.test", NEXT_PUBLIC_SUPABASE_ANON_KEY: "k" }),
      ),
    ).toEqual({ url: "https://build.example.test", key: "k" });
    expect(supabaseSettings(env({ WIZARD_SUPABASE_URL: "https://run.example.test" }))).toBeNull();
  });

  it("links to the demo's sign-up, or to the address set, and to nothing else", () => {
    expect(supabaseSignUpUrl(env({}))).toBe("https://gaik-demo.2.rahtiapp.fi/sign-up");
    expect(supabaseSignUpUrl(env({ GAIK_DEMO_URL: "https://demo.example.test/" }))).toBe(
      "https://demo.example.test/sign-up",
    );
    expect(supabaseSignUpUrl(env({ WIZARD_SUPABASE_SIGNUP_URL: "https://x.example.test/join" }))).toBe(
      "https://x.example.test/join",
    );
    expect(supabaseSignUpUrl(env({ WIZARD_SUPABASE_SIGNUP_URL: "" }))).toBeNull();
    expect(supabaseSignUpUrl(env({ WIZARD_SUPABASE_SIGNUP_URL: "javascript:alert(1)" }))).toBeNull();
  });

  it("takes access from access_requests only when asked to", () => {
    expect(accessRequestsEnabled(byRows)).toBe(true);
    expect(accessRequestsEnabled(env({}))).toBe(false);
  });
});

describe("who may use the wizard", () => {
  it("a row lets its user in when approved or granted the wizard", () => {
    expect(rowGrantsAccess({ status: "approved" })).toBe(true);
    expect(rowGrantsAccess({ status: "pending", wizard_access: true })).toBe(true);
    expect(rowGrantsAccess({ status: "pending", wizard_access: false })).toBe(false);
    expect(rowGrantsAccess({ status: "rejected" })).toBe(false);
    expect(rowGrantsAccess(null)).toBe(false);
  });

  it("lets in a confirmed account whose own row is approved", async () => {
    const c = client({ status: "approved", wizard_access: false });
    expect(await access(c, confirmed, byRows)).toBe(true);
    expect(c.from).toHaveBeenCalledWith("access_requests");
    expect(c.query.eq).toHaveBeenCalledWith("user_id", "u1");
  });

  it("refuses a pending account, a missing row and a row it cannot read", async () => {
    expect(await access(client({ status: "pending" }), confirmed, byRows)).toBe(false);
    expect(await access(client(null), confirmed, byRows)).toBe(false);
    expect(
      await access(client({ status: "approved" }, { message: "denied" }), confirmed, byRows),
    ).toBe(false);
  });

  it("refuses an address that is not confirmed, whatever its row says", async () => {
    const c = client({ status: "approved" });
    expect(await access(c, { ...confirmed, email_confirmed_at: null }, byRows)).toBe(false);
    expect(c.from).not.toHaveBeenCalled();
  });

  it("without access_requests only the listed addresses get in", async () => {
    const c = client({ status: "approved" });
    expect(await access(c, confirmed, env({}))).toBe(false);
    expect(
      await access(c, confirmed, env({ WIZARD_ALLOWED_EMAILS: "ada@example.test" })),
    ).toBe(true);
    expect(c.from).not.toHaveBeenCalled();
  });

  it("refuses when the query throws", async () => {
    const broken = {
      from: () => {
        throw new Error("network");
      },
    };
    expect(await access(broken as never, confirmed, byRows)).toBe(false);
  });
});
