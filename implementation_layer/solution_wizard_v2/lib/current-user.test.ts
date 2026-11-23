import { afterEach, describe, expect, it, vi } from "vitest";

const cookiesMock = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("next/headers", () => ({
  cookies: async () => cookiesMock,
}));

const supabaseAuthMock = vi.hoisted(() => ({ getUser: vi.fn() }));
const accessRow = vi.hoisted(() => ({ value: null as unknown }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    auth: supabaseAuthMock,
    from: () => {
      const query = {
        select: () => query,
        eq: () => query,
        maybeSingle: async () => ({ data: accessRow.value, error: null }),
      };
      return query;
    },
  }),
}));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  vi.clearAllMocks();
});

// DEV_AUTH is read once at module import time from NEXT_PUBLIC_DEV_AUTH, so
// each scenario stubs the env first and re-imports the module fresh.
async function importFresh() {
  vi.resetModules();
  return import("@/lib/current-user");
}

/** A cookie value the login action would have issued (lib/dev-session). */
async function signedCookie(email: string) {
  const { signDevSession } = await import("@/lib/dev-session");
  return { value: await signDevSession(email) };
}

describe("getCurrentUser — dev auth mode", () => {
  it("returns the user for a valid dev session cookie", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    cookiesMock.get.mockReturnValue(await signedCookie("dev@gaik.local"));
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toEqual({ email: "dev@gaik.local" });
  });

  it("returns null when no dev cookie is set", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    cookiesMock.get.mockReturnValue(undefined);
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });

  it("returns null for a cookie value that isn't a known dev user", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    cookiesMock.get.mockReturnValue(await signedCookie("not-a-dev-user@example.com"));
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });

  it("returns null for a hand-written cookie that only names a dev user", async () => {
    // The pre-P5 format, and exactly what an attacker would type into the browser.
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    cookiesMock.get.mockReturnValue({ value: "dev@gaik.local" });
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });

  it("never touches Supabase in dev mode", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    cookiesMock.get.mockReturnValue(await signedCookie("dev@gaik.local"));
    const { getCurrentUser } = await importFresh();
    await getCurrentUser();
    expect(supabaseAuthMock.getUser).not.toHaveBeenCalled();
  });
});

describe("getCurrentUser — Supabase mode", () => {
  it("returns the Supabase user's email when signed in", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "");
    vi.stubEnv("WIZARD_ALLOWED_EMAILS", "real@gaik.local");
    supabaseAuthMock.getUser.mockResolvedValue({
      data: { user: { email: "real@gaik.local", email_confirmed_at: "2026-11-01T10:00:00Z" } },
    });
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toEqual({ email: "real@gaik.local" });
  });

  it("returns null for a signed-in Supabase account that is not listed", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "");
    vi.stubEnv("WIZARD_ALLOWED_EMAILS", "someone-else@gaik.local");
    supabaseAuthMock.getUser.mockResolvedValue({
      data: { user: { email: "real@gaik.local", email_confirmed_at: "2026-11-01T10:00:00Z" } },
    });
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });

  it("returns null for a listed account whose address is not confirmed", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "");
    vi.stubEnv("WIZARD_ALLOWED_EMAILS", "real@gaik.local");
    supabaseAuthMock.getUser.mockResolvedValue({
      data: { user: { email: "real@gaik.local", email_confirmed_at: null } },
    });
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });

  it("returns null when Supabase has no signed-in user", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "");
    supabaseAuthMock.getUser.mockResolvedValue({ data: { user: null } });
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });
});


describe("getCurrentUser — Supabase sign-in on a dev-login image", () => {
  const user = { id: "u1", email: "ada@gaik.local", email_confirmed_at: "2026-11-20T10:00:00Z" };

  it("ignores a dev cookie and takes access from the demo's row", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    vi.stubEnv("WIZARD_AUTH_MODE", "supabase");
    vi.stubEnv("WIZARD_SUPABASE_ACCESS", "access_requests");
    cookiesMock.get.mockReturnValue(await signedCookie("dev@gaik.local"));
    supabaseAuthMock.getUser.mockResolvedValue({ data: { user } });
    accessRow.value = { status: "approved" };
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toEqual({ email: "ada@gaik.local" });
  });

  it("returns null while the demo has not approved the account", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH", "true");
    vi.stubEnv("WIZARD_AUTH_MODE", "supabase");
    vi.stubEnv("WIZARD_SUPABASE_ACCESS", "access_requests");
    supabaseAuthMock.getUser.mockResolvedValue({ data: { user } });
    accessRow.value = { status: "pending", wizard_access: false };
    const { getCurrentUser } = await importFresh();
    expect(await getCurrentUser()).toBeNull();
  });
});
