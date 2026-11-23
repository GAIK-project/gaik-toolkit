import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiGetBpmnMapping: vi.fn(),
}));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { GET } from "@/app/api/sessions/[id]/bpmn/mapping/route";
import { requireOwnedSession } from "@/lib/session-access";
import { apiGetBpmnMapping, wizardApiEnabled } from "@/lib/wizard-api-client";

const TRACE = "trace-mapping-0001";
const params = { params: Promise.resolve({ id: "s1" }) };
const get = (query = "") =>
  GET(new NextRequest(`http://localhost/api/sessions/s1/bpmn/mapping${query}`, { headers: { "x-trace-id": TRACE } }), params);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(wizardApiEnabled).mockReturnValue(true);
  vi.mocked(requireOwnedSession).mockResolvedValue({ user: { email: "dev@gaik.local" }, session: {} } as never);
});

describe("GET /sessions/[id]/bpmn/mapping", () => {
  it("answers 404 for a session that is not the caller's, without asking the api", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);
    expect((await get()).status).toBe(404);
    expect(apiGetBpmnMapping).not.toHaveBeenCalled();
  });

  it("answers 503 needs_wizard_api in mock mode", async () => {
    vi.mocked(wizardApiEnabled).mockReturnValue(false);
    const res = await get();
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "needs_wizard_api" });
  });

  it("forwards data_objects and passes the mapping on, uncached", async () => {
    const mapping = { mapping: { Task_s1: { kind: "step", blueprint_path: "workflow.steps[0]" } } };
    vi.mocked(apiGetBpmnMapping).mockImplementation(async () => Response.json(mapping));

    const full = await get();
    const compact = await get("?data_objects=0");

    expect(full.status).toBe(200);
    expect(full.headers.get("cache-control")).toBe("no-store");
    expect(await full.json()).toEqual(mapping);
    expect(compact.status).toBe(200);
    expect(apiGetBpmnMapping).toHaveBeenNthCalledWith(1, "s1", { dataObjects: true });
    expect(apiGetBpmnMapping).toHaveBeenNthCalledWith(2, "s1", { dataObjects: false });
  });

  it("refuses a data_objects other than 0 or 1", async () => {
    expect((await get("?data_objects=yes")).status).toBe(400);
    expect(apiGetBpmnMapping).not.toHaveBeenCalled();
  });
});
