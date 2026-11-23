import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" } })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardAgentChatEnabled: vi.fn(() => true),
  apiCreatePocCheck: vi.fn(),
}));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/poc/check/route";
import { apiCreatePocCheck } from "@/lib/wizard-api-client";

const TRACE = "trace-check-0001";

function post() {
  const req = new NextRequest("http://localhost/api/sessions/s1/poc/check", {
    method: "POST",
    headers: { "x-trace-id": TRACE },
  });
  return POST(req, { params: Promise.resolve({ id: "s1" }) });
}

describe("PoC preflight relay", () => {
  beforeEach(() => {
    vi.mocked(apiCreatePocCheck).mockReset();
  });

  it("passes a busy preflight on with its Retry-After", async () => {
    vi.mocked(apiCreatePocCheck).mockResolvedValue(
      Response.json(
        { detail: { error: "sandbox_busy", message: "the sandbox is busy; try again in a minute" } },
        { status: 429, headers: { "Retry-After": "30" } },
      ),
    );
    const res = await post();
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("30");
    expect((await res.json()).detail.error).toBe("sandbox_busy");
  });

  it("relays a started check unchanged", async () => {
    vi.mocked(apiCreatePocCheck).mockResolvedValue(
      Response.json({ run_id: "r1", phase: "pending", version: "v1" }, { status: 201 }),
    );
    const res = await post();
    expect(res.status).toBe(201);
    expect((await res.json()).run_id).toBe("r1");
  });

  it("turns an unknown code carrying a Kubernetes message into the generic message", async () => {
    vi.mocked(apiCreatePocCheck).mockResolvedValue(
      Response.json(
        { detail: { error: "ApiException", message: "(403) Forbidden: jobs.batch is forbidden in namespace gaik-sandbox" } },
        { status: 500 },
      ),
    );
    const res = await post();
    const text = await res.text();
    expect(text).not.toContain("jobs.batch");
    expect(text).not.toContain("gaik-sandbox");
    expect(JSON.parse(text).detail).toMatchObject({ error: "internal_error", trace_id: TRACE });
  });

  it("keeps the 409 for a package that is not complete", async () => {
    vi.mocked(apiCreatePocCheck).mockResolvedValue(
      Response.json({ detail: { error: "conflict", message: "no PoC package to check yet" } }, { status: 409 }),
    );
    const res = await post();
    expect(res.status).toBe(409);
    expect((await res.json()).detail).toMatchObject({ error: "conflict", message: "no PoC package to check yet" });
  });
});
