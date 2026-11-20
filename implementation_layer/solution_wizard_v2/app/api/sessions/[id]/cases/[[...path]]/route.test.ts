import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" } })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiCases: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { DELETE, GET, POST } from "@/app/api/sessions/[id]/cases/[[...path]]/route";
import { audit } from "@/lib/audit";
import { dictionary } from "@/lib/i18n";
import { apiCases } from "@/lib/wizard-api-client";

const TRACE = "trace-cases-001";
const CASE = "0f8fad5b-d9cb-469f-a165-70867728950e";

function call(method: "GET" | "POST" | "DELETE", path: string[], body?: unknown) {
  const req = new NextRequest(`http://localhost/api/sessions/s1/cases/${path.join("/")}`, {
    method,
    headers: { "x-trace-id": TRACE, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const handler = method === "GET" ? GET : method === "POST" ? POST : DELETE;
  return handler(req, { params: Promise.resolve({ id: "s1", path }) });
}

describe("cases relay", () => {
  beforeEach(() => {
    vi.mocked(apiCases).mockReset();
    vi.mocked(audit).mockReset();
  });

  it("relays a case unchanged", async () => {
    vi.mocked(apiCases).mockResolvedValue(Response.json({ id: CASE, status: "draft" }));
    const res = await call("GET", [CASE]);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ id: CASE, status: "draft" });
  });

  it("keeps a review refused for a missing required field", async () => {
    const detail = { error: "case_state", message: "invoice_number is required", trace_id: TRACE };
    vi.mocked(apiCases).mockResolvedValue(Response.json({ detail }, { status: 409 }));
    const res = await call("POST", [CASE, "review"], { action: "approve" });
    expect(res.status).toBe(409);
    expect((await res.json()).detail).toEqual(detail);
  });

  it("passes on the removal of a case and writes it to the audit trail", async () => {
    vi.mocked(apiCases).mockResolvedValue(new Response(null, { status: 204 }));
    const res = await call("DELETE", [CASE]);
    expect(res.status).toBe(204);
    expect(vi.mocked(apiCases).mock.calls[0].slice(0, 2)).toEqual(["s1", CASE]);
    expect(vi.mocked(apiCases).mock.calls[0][2]).toMatchObject({ method: "DELETE" });
    expect(vi.mocked(audit)).toHaveBeenCalledWith("case.delete", expect.objectContaining({ outcome: "success" }));
  });

  it("keeps the api's refusal to remove a case that was sent, and audits nothing", async () => {
    const detail = {
      error: "case_state",
      message: "the case is review; only a case still waiting for its input can be removed",
      trace_id: TRACE,
    };
    vi.mocked(apiCases).mockResolvedValue(Response.json({ detail }, { status: 409 }));
    const res = await call("DELETE", [CASE]);
    expect(res.status).toBe(409);
    expect((await res.json()).detail).toEqual(detail);
    expect(vi.mocked(audit)).not.toHaveBeenCalled();
  });

  it("removes nothing but a case or one of its input files", async () => {
    for (const path of [[], ["model"], ["not-a-case"], [CASE, "review"], [CASE, "inputs"], [CASE, "x", "y"]]) {
      const res = await call("DELETE", path);
      expect(res.status, path.join("/")).toBe(404);
    }
    expect(vi.mocked(apiCases)).not.toHaveBeenCalled();
    // An input file is still named as an input file in the audit trail.
    vi.mocked(apiCases).mockResolvedValue(new Response(null, { status: 204 }));
    expect((await call("DELETE", [CASE, "inputs", "report.wav"])).status).toBe(204);
    expect(vi.mocked(audit)).toHaveBeenCalledWith("case.input.delete", expect.anything());
  });

  it("relays copying a compatible PoC test file into a case and writes it to the audit trail", async () => {
    vi.mocked(apiCases).mockResolvedValue(
      Response.json({ name: "report.wav", bytes: 2048, task: "T_report" }, { status: 201 }),
    );
    const res = await call("POST", [CASE, "inputs", "from-poc"], {
      filename: "report.wav",
      task: "T_report",
    });
    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ name: "report.wav", bytes: 2048, task: "T_report" });
    expect(vi.mocked(apiCases).mock.calls[0].slice(0, 2)).toEqual(["s1", `${CASE}/inputs/from-poc`]);
    expect(vi.mocked(audit)).toHaveBeenCalledWith(
      "case.input.upload",
      expect.objectContaining({ outcome: "success", action: `${CASE}/inputs/from-poc` }),
    );
  });

  it("turns a BPMN parser error with a server path into the generic message", async () => {
    vi.mocked(apiCases).mockResolvedValue(
      Response.json(
        { detail: "workflow.bpmn does not parse: /srv/wizard/out/abc/workflow.bpmn line 3, column 1" },
        { status: 409 },
      ),
    );
    const res = await call("GET", ["model"]);
    const text = await res.text();
    expect(res.status).toBe(409);
    expect(text).not.toContain("/srv/wizard");
    expect(JSON.parse(text).detail.message).toBe(dictionary("en").errorGeneric.replace("{trace}", TRACE));
  });
});
