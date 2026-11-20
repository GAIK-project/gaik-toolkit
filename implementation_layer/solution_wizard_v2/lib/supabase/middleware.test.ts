import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const state = vi.hoisted(() => ({ user: null as unknown, row: null as unknown }));
vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({
    auth: { getUser: async () => ({ data: { user: state.user } }) },
    from: () => {
      const query = {
        select: () => query,
        eq: () => query,
        maybeSingle: async () => ({ data: state.row, error: null }),
      };
      return query;
    },
  }),
}));

import { updateSession } from "@/lib/supabase/middleware";
import { forgetAccessReads } from "@/lib/supabase-auth";

const confirmed = { id: "u1", email: "ada@gaik.local", email_confirmed_at: "2026-11-20T10:00:00Z" };

function configure() {
  vi.stubEnv("WIZARD_SUPABASE_URL", "https://project.example.test");
  vi.stubEnv("WIZARD_SUPABASE_KEY", "publishable-key");
  vi.stubEnv("WIZARD_SUPABASE_ACCESS", "access_requests");
}

const request = (path: string) => new NextRequest(`https://wizard.example.test${path}`);

afterEach(() => {
  forgetAccessReads();
  vi.unstubAllEnvs();
  state.user = null;
  state.row = null;
});

describe("updateSession (Supabase sign-in)", () => {
  it("lets an approved account through", async () => {
    configure();
    state.user = confirmed;
    state.row = { status: "approved" };
    const res = await updateSession(request("/sessions/abc"));
    expect(res.headers.get("location")).toBeNull();
    expect(res.status).toBe(200);
  });

  it("answers an API call without access with 401, not a page", async () => {
    configure();
    const res = await updateSession(request("/api/sessions"));
    expect(res.status).toBe(401);
  });

  it("sends a signed-in account still waiting to the login page with a notice", async () => {
    configure();
    state.user = confirmed;
    state.row = { status: "pending" };
    const res = await updateSession(request("/"));
    expect(res.headers.get("location")).toBe("https://wizard.example.test/login?error=pending");
  });

  it("sends an anonymous visitor to the login page and leaves the login page open", async () => {
    configure();
    expect((await updateSession(request("/"))).headers.get("location")).toBe(
      "https://wizard.example.test/login",
    );
    expect((await updateSession(request("/login"))).status).toBe(200);
  });

  it("opens nothing but the public pages when the project is not configured", async () => {
    expect((await updateSession(request("/api/sessions"))).status).toBe(401);
    expect((await updateSession(request("/"))).headers.get("location")).toBe(
      "https://wizard.example.test/login?error=unavailable",
    );
    expect((await updateSession(request("/privacy"))).status).toBe(200);
  });
});
