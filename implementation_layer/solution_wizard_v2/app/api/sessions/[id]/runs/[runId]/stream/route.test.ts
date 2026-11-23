import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" } })),
}));
vi.mock("@/lib/wizard-api-client", () => ({ apiStreamPocRun: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { GET } from "@/app/api/sessions/[id]/runs/[runId]/stream/route";
import { dictionary } from "@/lib/i18n";
import { apiStreamPocRun } from "@/lib/wizard-api-client";

const TRACE = "trace-stream-001";

function get() {
  const req = new NextRequest("http://localhost/api/sessions/s1/runs/r1/stream", {
    headers: { "x-trace-id": TRACE },
  });
  return GET(req, { params: Promise.resolve({ id: "s1", runId: "r1" }) });
}

function sse(...frames: object[]): Response {
  return new Response(frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join(""), {
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("PoC run stream relay", () => {
  beforeEach(() => {
    vi.mocked(apiStreamPocRun).mockReset();
  });

  it("passes the run's log and done frames on", async () => {
    vi.mocked(apiStreamPocRun).mockResolvedValue(
      sse({ log: "step 1" }, { done: true, phase: "failed", reason: "ValueError: bad input" }),
    );
    const text = await (await get()).text();
    expect(text).toContain('"log":"step 1"');
    expect(text).toContain('"reason":"ValueError: bad input"');
  });

  it("rewrites an error frame that carries a Kubernetes message", async () => {
    vi.mocked(apiStreamPocRun).mockResolvedValue(
      sse({ log: "step 1" }, { error: true, message: "(410) Gone: watch closed, resourceVersion too old" }),
    );
    const text = await (await get()).text();
    expect(text).not.toContain("resourceVersion");
    const error = JSON.parse(text.split("\n\n")[1].slice(6));
    expect(error).toEqual({
      error: true,
      code: "internal_error",
      message: dictionary("en").errorGeneric.replace("{trace}", TRACE),
      trace_id: TRACE,
    });
  });

  it("keeps a known code's error frame", async () => {
    const frame = { error: true, code: "agent_capacity", message: "The wizard is busy.", trace_id: TRACE };
    vi.mocked(apiStreamPocRun).mockResolvedValue(sse(frame));
    expect(JSON.parse((await (await get()).text()).slice(6))).toEqual(frame);
  });

  it("does not relay the text body of a failed stream", async () => {
    vi.mocked(apiStreamPocRun).mockResolvedValue(
      new Response("Internal Server Error: /app/wizard_api/routers/sessions.py line 1100", { status: 500 }),
    );
    const res = await get();
    const text = await res.text();
    expect(res.status).toBe(500);
    expect(text).not.toContain("sessions.py");
  });

  it("keeps a run that is not this session's a 404", async () => {
    vi.mocked(apiStreamPocRun).mockResolvedValue(
      Response.json({ detail: { error: "not_found", message: "run not found" } }, { status: 404 }),
    );
    const res = await get();
    expect(res.status).toBe(404);
    expect((await res.json()).detail).toMatchObject({ error: "not_found", message: "run not found" });
  });
});
