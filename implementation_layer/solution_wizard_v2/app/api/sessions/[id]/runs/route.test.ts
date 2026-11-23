import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// The relay's own decision is under test: which of the api's error answers
// reach the browser as they are, and which become the generic message.
vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" } })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardAgentChatEnabled: vi.fn(() => true),
  apiCreatePocRun: vi.fn(),
}));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/runs/route";
import { dictionary } from "@/lib/i18n";
import { apiCreatePocRun, wizardAgentChatEnabled } from "@/lib/wizard-api-client";

const TRACE = "trace-runs-0001";
const generic = dictionary("en").errorGeneric.replace("{trace}", TRACE);

function post() {
  const req = new NextRequest("http://localhost/api/sessions/s1/runs", {
    method: "POST",
    headers: { "x-trace-id": TRACE },
  });
  return POST(req, { params: Promise.resolve({ id: "s1" }) });
}

describe("PoC run relay", () => {
  beforeEach(() => {
    vi.mocked(apiCreatePocRun).mockReset();
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
  });

  it("relays a started run unchanged", async () => {
    vi.mocked(apiCreatePocRun).mockResolvedValue(
      Response.json({ run_id: "r1", phase: "pending" }, { status: 201 }),
    );
    const res = await post();
    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ run_id: "r1", phase: "pending" });
  });

  it("keeps sandbox_busy, its message and when to try again", async () => {
    const detail = { error: "sandbox_busy", message: "the sandbox is busy: 3 runs are going", trace_id: TRACE };
    vi.mocked(apiCreatePocRun).mockResolvedValue(
      Response.json({ detail }, { status: 429, headers: { "Retry-After": "60" } }),
    );
    const res = await post();
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("60");
    expect((await res.json()).detail).toEqual(detail);
  });

  it("keeps an incomplete package's 409 and its problems", async () => {
    const detail = {
      error: "poc_package_incomplete",
      problems: ["run_poc.py is missing"],
      message: "the package is not complete: run_poc.py is missing",
      trace_id: TRACE,
    };
    vi.mocked(apiCreatePocRun).mockResolvedValue(Response.json({ detail }, { status: 409 }));
    const res = await post();
    expect(res.status).toBe(409);
    expect((await res.json()).detail).toEqual(detail);
  });

  it("turns a raw exception with a server path into the generic message", async () => {
    vi.mocked(apiCreatePocRun).mockResolvedValue(
      Response.json(
        { detail: "no sandbox namespace — set WIZARD_SANDBOX_NAMESPACE at /srv/wizard/deploy" },
        { status: 503 },
      ),
    );
    const res = await post();
    const text = await res.text();
    expect(res.status).toBe(503);
    expect(text).not.toContain("/srv/wizard");
    expect(text).not.toContain("WIZARD_SANDBOX_NAMESPACE");
    expect(JSON.parse(text).detail).toEqual({ error: "internal_error", message: generic, trace_id: TRACE });
  });

  it("turns a traceback in a non-JSON body into the generic message", async () => {
    vi.mocked(apiCreatePocRun).mockResolvedValue(
      new Response('Traceback (most recent call last):\n  File "/app/wizard_api/main.py"', { status: 500 }),
    );
    const res = await post();
    const text = await res.text();
    expect(res.status).toBe(500);
    expect(text).not.toContain("Traceback");
    expect(JSON.parse(text).detail.message).toBe(generic);
  });

  it("says the server did not answer, without the error's text", async () => {
    vi.mocked(apiCreatePocRun).mockRejectedValue(new Error("connect ECONNREFUSED 10.0.0.7:8100"));
    const res = await post();
    const text = await res.text();
    expect(res.status).toBe(502);
    expect(text).not.toContain("ECONNREFUSED");
    expect(JSON.parse(text).detail.message).toBe(
      dictionary("en").errorUnreachable.replace("{trace}", TRACE),
    );
  });

  it("says the sandbox is unavailable without naming the setting", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(false);
    const res = await post();
    expect(res.status).toBe(503);
    const detail = (await res.json()).detail;
    expect(detail.error).toBe("sandbox_unavailable");
    expect(detail.message).not.toContain("wizard_api");
  });
});
