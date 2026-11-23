import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// The route's collaborators are mocked: the test exercises the owner check,
// the size cap, mock mode and what of wizard_api's answer reaches the browser.
vi.mock("@/lib/session-access", () => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiPostOperations: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/blueprint/operations/route";
import { requireOwnedSession } from "@/lib/session-access";
import { apiPostOperations, wizardApiEnabled } from "@/lib/wizard-api-client";
import { audit } from "@/lib/audit";

const TRACE = "trace-ops-0001";
const params = { params: Promise.resolve({ id: "s1" }) };
const OPS = { base_version: 3, operations: [{ op: "rename_step", step_id: "s1", name: "Read" }] };

function post(body: unknown, headers: Record<string, string> = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return POST(
    new NextRequest("http://localhost/api/sessions/s1/blueprint/operations", {
      method: "POST",
      headers: {
        "x-trace-id": TRACE,
        "content-type": "application/json",
        "content-length": String(Buffer.byteLength(text)),
        ...headers,
      },
      body: text,
    }),
    params,
  );
}

const SESSION = {
  id: "s1",
  user_id: "owner-1",
  title: "t",
  step: 6,
  status: "active",
  gate_statuses: { gate_1: "approved" },
  metadata: { secret_note: "x" },
  output_dir: "/srv/wizard/sessions/s1",
  active_version: 4,
  versions: [],
  blueprint: { name: "b", description: "", goal: "", steps: [] },
  messages: [{ id: "m", role: "user", content: "hi" }],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(wizardApiEnabled).mockReturnValue(true);
  vi.mocked(requireOwnedSession).mockResolvedValue({
    user: { email: "dev@gaik.local" },
    session: { id: "s1" },
  } as never);
});

describe("POST /sessions/[id]/blueprint/operations", () => {
  it("the operations route refuses a request it does not own", async () => {
    // The route's own check (requireOwnedSession): a session that is not the
    // signed-in user's is not found, and wizard_api is never asked. wizard_api
    // checks the X-Wizard-User-Id that outgoingHeaders() adds as well.
    vi.mocked(requireOwnedSession).mockResolvedValue(null);

    const res = await post(OPS);

    expect(res.status).toBe(404);
    expect(apiPostOperations).not.toHaveBeenCalled();
  });

  it("the operations route refuses a body over 64 KB with 413", async () => {
    const big = { ...OPS, operations: [{ op: "rename_step", step_id: "s1", name: "x".repeat(70 * 1024) }] };

    const res = await post(big);

    expect(res.status).toBe(413);
    expect((await res.json()).detail.error).toBe("too_large");
    expect(apiPostOperations).not.toHaveBeenCalled();
  });

  it("refuses on the declared length alone, and a body that does not say its length", async () => {
    const declared = await post(OPS, { "content-length": String(65 * 1024) });
    expect(declared.status).toBe(413);

    const noLength = await POST(
      new NextRequest("http://localhost/api/sessions/s1/blueprint/operations", {
        method: "POST",
        body: JSON.stringify(OPS),
      }),
      params,
    );
    expect(noLength.status).toBe(411);
    expect(apiPostOperations).not.toHaveBeenCalled();
  });

  it("refuses a body that is not JSON", async () => {
    const res = await post("not json");
    expect(res.status).toBe(400);
    expect(apiPostOperations).not.toHaveBeenCalled();
  });

  it("answers 503 needs_wizard_api in mock mode", async () => {
    vi.mocked(wizardApiEnabled).mockReturnValue(false);

    const res = await post(OPS);

    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "needs_wizard_api" });
    expect(apiPostOperations).not.toHaveBeenCalled();
  });

  it("forwards the body and answers with the edit's result, without the session's internals", async () => {
    vi.mocked(apiPostOperations).mockResolvedValue(
      Response.json({ session: SESSION, warnings: ["w"], needs_attention: ["n"], bpmn_changed: true }),
    );

    const res = await post(OPS);

    expect(res.status).toBe(200);
    expect(apiPostOperations).toHaveBeenCalledWith("s1", OPS);
    const body = await res.json();
    expect(body).toEqual({
      session: {
        id: "s1",
        step: 6,
        gate_statuses: { gate_1: "approved" },
        active_version: 4,
        blueprint: SESSION.blueprint,
      },
      warnings: ["w"],
      needs_attention: ["n"],
      bpmn_changed: true,
    });
    expect(JSON.stringify(body)).not.toContain("/srv/wizard");
    expect(audit).toHaveBeenCalledWith("blueprint.ops", expect.objectContaining({ outcome: "success" }));
  });

  it.each([
    [409, { error: "changed_elsewhere", message: "The blueprint has changed.", trace_id: TRACE }],
    [409, { error: "no_draft", message: "Nothing to edit yet.", trace_id: TRACE }],
    [409, { error: "agent_busy", message: "The wizard is replying.", trace_id: TRACE }],
    [
      422,
      {
        error: "invalid_operation",
        message: "No step s9.",
        field: "operations[0].step_id",
        index: 0,
        code: "not_found",
        trace_id: TRACE,
      },
    ],
  ])("the routes pass 409 and 422 bodies through unchanged (%i)", async (status, detail) => {
    vi.mocked(apiPostOperations).mockResolvedValue(Response.json({ detail }, { status }));

    const res = await post(OPS);

    expect(res.status).toBe(status);
    expect(await res.json()).toEqual({ detail });
    expect(audit).toHaveBeenCalledWith("blueprint.ops", expect.objectContaining({ outcome: "denied" }));
  });

  it("does not pass on an error it does not know", async () => {
    vi.mocked(apiPostOperations).mockResolvedValue(
      Response.json({ detail: { error: "OSError", message: "/srv/wizard/sessions/s1 denied" } }, { status: 500 }),
    );

    const res = await post(OPS);
    const text = await res.text();

    expect(res.status).toBe(500);
    expect(text).not.toContain("/srv/wizard");
    expect(JSON.parse(text).detail).toMatchObject({ error: "internal_error", trace_id: TRACE });
  });

  it("answers 502, audited as an error, when a 2xx from wizard_api is not JSON", async () => {
    vi.mocked(apiPostOperations).mockResolvedValue(new Response("<html>proxy page</html>", { status: 200 }));

    const res = await post(OPS);
    const text = await res.text();

    expect(res.status).toBe(502);
    expect(text).not.toContain("proxy page");
    expect(JSON.parse(text).detail.error).toBe("upstream_unreachable");
    expect(audit).toHaveBeenCalledWith("blueprint.ops", expect.objectContaining({ outcome: "error" }));
    expect(audit).not.toHaveBeenCalledWith("blueprint.ops", expect.objectContaining({ outcome: "success" }));
  });

  it("answers 502 when wizard_api cannot be reached", async () => {
    vi.mocked(apiPostOperations).mockRejectedValue(new Error("connect ECONNREFUSED"));

    const res = await post(OPS);

    expect(res.status).toBe(502);
    expect((await res.json()).detail.error).toBe("upstream_unreachable");
  });
});
