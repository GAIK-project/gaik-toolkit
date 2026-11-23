import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// Collaborators are mocked so the test exercises the route's own decisions:
// which api answers reach the browser as what.
vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" } })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiGetPocZip: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));

import { GET } from "@/app/api/sessions/[id]/poc/download/route";
import { apiGetPocZip } from "@/lib/wizard-api-client";

function get() {
  const req = new NextRequest("http://localhost/api/sessions/s1/poc/download");
  return GET(req, { params: Promise.resolve({ id: "s1" }) });
}

describe("PoC download route", () => {
  beforeEach(() => vi.mocked(apiGetPocZip).mockReset());

  it("relays the zip", async () => {
    vi.mocked(apiGetPocZip).mockResolvedValue(
      new Response(new Uint8Array([80, 75, 3, 4]), { status: 200 }),
    );
    const res = await get();
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/zip");
  });

  it("passes on an incomplete package as 409 with the api's reasons", async () => {
    const detail = {
      error: "poc_package_incomplete",
      message: "the generated package is not complete: run_poc.py is missing",
      problems: ["run_poc.py is missing"],
    };
    vi.mocked(apiGetPocZip).mockResolvedValue(Response.json({ detail }, { status: 409 }));
    const res = await get();
    expect(res.status).toBe(409);
    const body = (await res.json()).detail;
    expect(body).toMatchObject(detail);
    expect(typeof body.trace_id).toBe("string");
  });

  it("does not pass on a 409 whose body is not a known refusal", async () => {
    vi.mocked(apiGetPocZip).mockResolvedValue(
      Response.json({ detail: "PermissionError: /srv/wizard/out/poc" }, { status: 409 }),
    );
    const res = await get();
    expect(res.status).toBe(409);
    const text = await res.text();
    expect(text).not.toContain("/srv/wizard");
    expect(JSON.parse(text).detail.error).toBe("internal_error");
  });

  it("says nothing was generated on 404", async () => {
    vi.mocked(apiGetPocZip).mockResolvedValue(new Response("", { status: 404 }));
    expect((await get()).status).toBe(404);
  });

  it("reports any other api failure as 502", async () => {
    vi.mocked(apiGetPocZip).mockResolvedValue(new Response("", { status: 401 }));
    expect((await get()).status).toBe(502);
  });
});
