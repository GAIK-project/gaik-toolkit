import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({
    user: { email: "dev@gaik.local" },
    session: { step: 10, blueprint: { name: "b", steps: [] } },
  })),
}));
vi.mock("@/lib/bpmn-spike", () => ({
  BPMN_VISUAL_STEP: 5,
  hasBpmnSpike: vi.fn(() => true),
}));
vi.mock("@/lib/bpmn-generate", () => ({
  fetchBpmnXmlForSession: vi.fn(async () => "<bpmn:definitions/>"),
}));

import { GET } from "@/app/api/sessions/[id]/bpmn/route";
import { fetchBpmnXmlForSession } from "@/lib/bpmn-generate";

function get(query = "") {
  const req = new NextRequest(`http://localhost/api/sessions/s1/bpmn${query}`);
  return GET(req, { params: Promise.resolve({ id: "s1" }) });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GET /sessions/[id]/bpmn — data objects", () => {
  it("draws the data objects by default and with data_objects=1", async () => {
    for (const query of ["", "?data_objects=1"]) {
      const res = await get(query);
      expect(res.status).toBe(200);
      expect(await res.text()).toBe("<bpmn:definitions/>");
    }
    const calls = vi.mocked(fetchBpmnXmlForSession).mock.calls;
    expect(calls.map((c) => c[2])).toEqual([{ dataObjects: true }, { dataObjects: true }]);
  });

  it("passes data_objects=0 on, for wizard_api and for the local generator alike", async () => {
    const res = await get("?data_objects=0");
    expect(res.status).toBe(200);
    expect(fetchBpmnXmlForSession).toHaveBeenCalledWith("s1", { name: "b", steps: [] }, { dataObjects: false });
  });

  it("refuses any other value without drawing", async () => {
    const res = await get("?data_objects=yes");
    expect(res.status).toBe(400);
    expect(fetchBpmnXmlForSession).not.toHaveBeenCalled();
  });
});
