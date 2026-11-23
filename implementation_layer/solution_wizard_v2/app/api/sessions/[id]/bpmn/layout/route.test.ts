import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiPutBpmnLayout: vi.fn(),
}));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { PUT } from "@/app/api/sessions/[id]/bpmn/layout/route";
import { requireOwnedSession } from "@/lib/session-access";
import { apiPutBpmnLayout, wizardApiEnabled } from "@/lib/wizard-api-client";

const TRACE = "trace-layout-0001";
const params = { params: Promise.resolve({ id: "s1" }) };
const LAYOUT = { shapes: { Task_s1: { x: 10, y: 20 }, Task_s2: null }, edges: {} };

function put(body: unknown, query = "", headers: Record<string, string> = {}) {
  const text = JSON.stringify(body);
  return PUT(
    new NextRequest(`http://localhost/api/sessions/s1/bpmn/layout${query}`, {
      method: "PUT",
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(wizardApiEnabled).mockReturnValue(true);
  vi.mocked(requireOwnedSession).mockResolvedValue({ user: { email: "dev@gaik.local" }, session: {} } as never);
});

describe("PUT /sessions/[id]/bpmn/layout", () => {
  it("answers 404 for a session that is not the caller's, without asking the api", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);
    expect((await put(LAYOUT)).status).toBe(404);
    expect(apiPutBpmnLayout).not.toHaveBeenCalled();
  });

  it("answers 503 needs_wizard_api in mock mode", async () => {
    vi.mocked(wizardApiEnabled).mockReturnValue(false);
    const res = await put(LAYOUT);
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "needs_wizard_api" });
  });

  it("refuses a body over 64 KB with 413", async () => {
    const res = await put({ shapes: { a: { x: 1, y: 1, pad: "x".repeat(70 * 1024) } } });
    expect(res.status).toBe(413);
    expect(apiPutBpmnLayout).not.toHaveBeenCalled();
  });

  it("refuses a data_objects other than 0 or 1", async () => {
    expect((await put(LAYOUT, "?data_objects=2")).status).toBe(400);
    expect(apiPutBpmnLayout).not.toHaveBeenCalled();
  });

  it("forwards the layout with the drawing mode and answers 204", async () => {
    vi.mocked(apiPutBpmnLayout).mockImplementation(async () => new Response(null, { status: 204 }));

    const full = await put(LAYOUT);
    const compact = await put(LAYOUT, "?data_objects=0");

    expect(full.status).toBe(204);
    expect(compact.status).toBe(204);
    expect(apiPutBpmnLayout).toHaveBeenNthCalledWith(1, "s1", LAYOUT, { dataObjects: true });
    expect(apiPutBpmnLayout).toHaveBeenNthCalledWith(2, "s1", LAYOUT, { dataObjects: false });
  });

  it("passes a 422 invalid_layout through unchanged", async () => {
    const detail = { error: "invalid_layout", message: "at most 1000 shapes", trace_id: TRACE };
    vi.mocked(apiPutBpmnLayout).mockResolvedValue(Response.json({ detail }, { status: 422 }));

    const res = await put(LAYOUT);

    expect(res.status).toBe(422);
    expect(await res.json()).toEqual({ detail });
  });
});
