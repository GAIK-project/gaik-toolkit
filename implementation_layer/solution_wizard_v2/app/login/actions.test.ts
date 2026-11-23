import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Made-up accounts and key, set before lib/auth reads the env.
vi.hoisted(() => {
  process.env.NEXT_PUBLIC_DEV_AUTH = "true";
  process.env.WIZARD_DEV_USERS = "alice@example.test:alice-pw,bob@example.test:bob-pw";
  process.env.DEV_AUTH_SECRET = "test-only-signing-key";
});

const state = vi.hoisted(() => ({
  forwardedFor: null as string | null,
  cookieSet: vi.fn(),
  audit: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({ set: state.cookieSet, get: vi.fn(), delete: vi.fn() }),
  headers: async () => ({
    get: (name: string) => (name === "x-forwarded-for" ? state.forwardedFor : null),
  }),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT ${url}`);
  },
}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({ createClient: vi.fn() }));
vi.mock("@/lib/audit", () => ({ audit: state.audit }));

import { resetDevLoginCounter } from "@/lib/login-throttle";
import { createClient } from "@/lib/supabase/server";
import { login } from "./actions";

function form(email: string, password: string): FormData {
  const f = new FormData();
  f.set("email", email);
  f.set("password", password);
  return f;
}

async function attempt(email: string, password: string): Promise<string> {
  try {
    await login(form(email, password));
  } catch (err) {
    return (err as Error).message.replace(/^REDIRECT /, "");
  }
  throw new Error("login did not redirect");
}

const lastAudit = () => state.audit.mock.calls.at(-1)?.[1];

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  process.env.WIZARD_DEV_LOGIN_MAX_FAILURES = "3";
  process.env.WIZARD_DEV_LOGIN_WINDOW_S = "600";
  process.env.WIZARD_DEV_LOGIN_LOCKOUT_S = "600";
  process.env.WIZARD_TRUSTED_PROXY_HOPS = "1";
  state.forwardedFor = "203.0.113.7";
  state.cookieSet.mockClear();
  state.audit.mockClear();
  resetDevLoginCounter();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("dev sign-in attempts are bounded", () => {
  it("lets the right password in under the limit", async () => {
    await attempt("alice@example.test", "wrong");
    await attempt("alice@example.test", "wrong");
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/");
    expect(state.cookieSet).toHaveBeenCalledTimes(1);
    expect(lastAudit()).toMatchObject({ outcome: "success" });
  });

  it("refuses the account at the limit, even with the right password", async () => {
    for (let i = 0; i < 3; i++) {
      expect(await attempt("alice@example.test", "wrong")).toBe("/login?error=credentials");
      expect(lastAudit()).toMatchObject({ outcome: "denied" });
      expect(lastAudit()).not.toHaveProperty("reason");
    }
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/login?error=credentials");
    expect(state.cookieSet).not.toHaveBeenCalled();
    expect(lastAudit()).toMatchObject({
      actor: "alice@example.test",
      outcome: "denied",
      reason: "throttled",
      mode: "dev",
    });
  });

  it("lets the account in again once the lockout is over", async () => {
    for (let i = 0; i < 3; i++) await attempt("alice@example.test", "wrong");
    vi.advanceTimersByTime(600_000);
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/");
  });

  it("forgets failures older than the window", async () => {
    await attempt("alice@example.test", "wrong");
    await attempt("alice@example.test", "wrong");
    vi.advanceTimersByTime(600_001);
    await attempt("alice@example.test", "wrong");
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/");
  });

  it("answers an unknown account the same way, so the bound reveals no account", async () => {
    for (let i = 0; i < 3; i++) {
      state.forwardedFor = `198.51.100.${i}`;
      await attempt("nobody@example.test", "wrong");
    }
    expect(await attempt("nobody@example.test", "wrong")).toBe("/login?error=credentials");
    expect(lastAudit()).toMatchObject({ reason: "throttled" });
  });

  it("counts per account: another account from another address is not refused", async () => {
    for (let i = 0; i < 3; i++) {
      state.forwardedFor = `198.51.100.${i}`;
      await attempt("alice@example.test", "wrong");
    }
    state.forwardedFor = "192.0.2.50";
    expect(await attempt("bob@example.test", "bob-pw")).toBe("/");
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/login?error=credentials");
  });

  it("counts per address: one address trying many accounts is refused", async () => {
    for (let i = 0; i < 3; i++) await attempt(`guess${i}@example.test`, "wrong");
    expect(await attempt("bob@example.test", "bob-pw")).toBe("/login?error=credentials");
    expect(lastAudit()).toMatchObject({ reason: "throttled" });
    state.forwardedFor = "192.0.2.50";
    expect(await attempt("bob@example.test", "bob-pw")).toBe("/");
  });

  it("uses the address the proxy appended, not one the client put in front", async () => {
    for (let i = 0; i < 3; i++) {
      state.forwardedFor = `10.9.9.${i}, 203.0.113.7`;
      await attempt(`guess${i}@example.test`, "wrong");
    }
    state.forwardedFor = "203.0.113.7";
    expect(await attempt("bob@example.test", "bob-pw")).toBe("/login?error=credentials");
  });

  it("ignores the forwarded header when no proxy is configured", async () => {
    delete process.env.WIZARD_TRUSTED_PROXY_HOPS;
    for (let i = 0; i < 3; i++) await attempt(`guess${i}@example.test`, "wrong");
    expect(await attempt("bob@example.test", "bob-pw")).toBe("/");
  });

  it("does not count successful sign-ins", async () => {
    for (let i = 0; i < 5; i++) {
      expect(await attempt("alice@example.test", "alice-pw")).toBe("/");
    }
    await attempt("alice@example.test", "wrong");
    await attempt("alice@example.test", "wrong");
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/");
  });
});


describe("Supabase sign-in on a dev-login image", () => {
  const user = { id: "u1", email: "ada@example.test", email_confirmed_at: "2026-11-20T10:00:00Z" };

  function supabaseWith(row: unknown) {
    const signOut = vi.fn(async () => ({}));
    const query = {
      select: () => query,
      eq: () => query,
      maybeSingle: async () => ({ data: row, error: null }),
    };
    vi.mocked(createClient).mockResolvedValue({
      auth: {
        signInWithPassword: vi.fn(async () => ({ data: { user }, error: null })),
        signOut,
      },
      from: () => query,
    } as never);
    return signOut;
  }

  beforeEach(() => {
    process.env.WIZARD_AUTH_MODE = "supabase";
    process.env.WIZARD_SUPABASE_ACCESS = "access_requests";
  });
  afterEach(async () => {
    (await import("@/lib/supabase-auth")).forgetAccessReads();
    delete process.env.WIZARD_AUTH_MODE;
    delete process.env.WIZARD_SUPABASE_ACCESS;
  });

  it("signs in through Supabase, not with the dev accounts", async () => {
    supabaseWith({ status: "approved" });
    expect(await attempt("alice@example.test", "alice-pw")).toBe("/");
    expect(lastAudit()).toMatchObject({ mode: "supabase", outcome: "success" });
  });

  it("signs an account the demo has not approved out again and says it waits", async () => {
    const signOut = supabaseWith({ status: "pending" });
    expect(await attempt("ada@example.test", "right-pw")).toBe("/login?error=pending");
    expect(signOut).toHaveBeenCalled();
    expect(lastAudit()).toMatchObject({ outcome: "denied", reason: "no_access", mode: "supabase" });
    expect(state.cookieSet).not.toHaveBeenCalled();
  });
});
