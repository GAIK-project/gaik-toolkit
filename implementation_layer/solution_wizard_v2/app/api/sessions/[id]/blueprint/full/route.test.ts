import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiGetFullBlueprint: vi.fn(),
  apiPutFullBlueprint: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { GET, PUT } from "@/app/api/sessions/[id]/blueprint/full/route";
import { requireOwnedSession } from "@/lib/session-access";
import { apiGetFullBlueprint, apiPutFullBlueprint, wizardApiEnabled } from "@/lib/wizard-api-client";
import { MAX_BLUEPRINT_CHARS } from "@/lib/blueprint-ops";

/** The route's cap: a blueprint at 4 bytes a character (UTF-8's most), and the body around it. */
const MAX_BODY_BYTES = 4 * MAX_BLUEPRINT_CHARS + 1024;

const TRACE = "trace-full-0001";
const params = { params: Promise.resolve({ id: "s1" }) };
const url = "http://localhost/api/sessions/s1/blueprint/full";
const get = () => GET(new NextRequest(url, { headers: { "x-trace-id": TRACE } }), params);

function put(body: unknown, headers: Record<string, string> = {}) {
  const text = JSON.stringify(body);
  return PUT(
    new NextRequest(url, {
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

describe("GET and PUT /sessions/[id]/blueprint/full", () => {
  it("answers 404 for a session that is not the caller's, without asking the api", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);
    expect((await get()).status).toBe(404);
    expect((await put({ base_version: 1, draft: {} })).status).toBe(404);
    expect(apiGetFullBlueprint).not.toHaveBeenCalled();
    expect(apiPutFullBlueprint).not.toHaveBeenCalled();
  });

  it("answers 503 needs_wizard_api in mock mode", async () => {
    vi.mocked(wizardApiEnabled).mockReturnValue(false);
    for (const res of [await get(), await put({ base_version: 1, draft: {} })]) {
      expect(res.status).toBe(503);
      expect(await res.json()).toEqual({ error: "needs_wizard_api" });
    }
  });

  it("passes the draft on, uncached", async () => {
    const full = {
      version: 3,
      draft: { workflow: { steps: [] } },
      readonly_sections: ["metadata"],
      draft_digest: "abc123",
    };
    vi.mocked(apiGetFullBlueprint).mockResolvedValue(Response.json(full));

    const res = await get();

    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual(full);
  });

  it("passes a 409 no_draft through unchanged", async () => {
    const detail = { error: "no_draft", message: "nothing yet", trace_id: TRACE };
    vi.mocked(apiGetFullBlueprint).mockResolvedValue(Response.json({ detail }, { status: 409 }));

    const res = await get();

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ detail });
  });

  it("takes a draft over 64 KB, up to the blueprint's own limit", async () => {
    vi.mocked(apiPutFullBlueprint).mockResolvedValue(
      Response.json({
        session: { id: "s1", step: 6, gate_statuses: {}, active_version: 4, output_dir: "/srv/x", blueprint: { name: "b" } },
        warnings: [],
        needs_attention: [],
        bpmn_changed: false,
      }),
    );
    const draft = { description: "x".repeat(200 * 1024) };

    const res = await put({ base_version: 3, base_digest: "abc123", draft });

    expect(res.status).toBe(200);
    expect(apiPutFullBlueprint).toHaveBeenCalledWith("s1", { base_version: 3, base_digest: "abc123", draft });
    const body = await res.json();
    expect(body.session).toEqual({ id: "s1", step: 6, gate_statuses: {}, active_version: 4, blueprint: { name: "b" } });
  });

  it("takes a blueprint of non-ASCII text over 1 MB in bytes: the api counts its characters", async () => {
    vi.mocked(apiPutFullBlueprint).mockResolvedValue(
      Response.json({ session: { id: "s1" }, warnings: [], needs_attention: [], bpmn_changed: false }),
    );
    // Under MAX_BLUEPRINT_CHARS characters, over it in UTF-8 bytes (ä is 2 bytes).
    const draft = { description: "ä".repeat(MAX_BLUEPRINT_CHARS - 1024) };

    const res = await put({ base_version: 3, base_digest: "abc123", draft });

    expect(res.status).toBe(200);
    expect(apiPutFullBlueprint).toHaveBeenCalled();
  });

  it("refuses a body over 4 bytes a character of the blueprint's limit with 413", async () => {
    const res = await put({ base_version: 3, base_digest: "abc123", draft: {} }, { "content-length": String(MAX_BODY_BYTES + 1) });
    expect(res.status).toBe(413);
    expect(apiPutFullBlueprint).not.toHaveBeenCalled();
  });

  it("passes a 409 changed_elsewhere through unchanged", async () => {
    const detail = { error: "changed_elsewhere", message: "The blueprint has changed.", trace_id: TRACE };
    vi.mocked(apiPutFullBlueprint).mockResolvedValue(Response.json({ detail }, { status: 409 }));

    const res = await put({ base_version: 3, base_digest: "old", draft: {} });

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ detail });
  });

  it("passes a 422 readonly_section through unchanged", async () => {
    const detail = { error: "readonly_section", message: "metadata is the server's", field: "metadata", trace_id: TRACE };
    vi.mocked(apiPutFullBlueprint).mockResolvedValue(Response.json({ detail }, { status: 422 }));

    const res = await put({ base_version: 3, base_digest: "abc123", draft: { metadata: {} } });

    expect(res.status).toBe(422);
    expect(await res.json()).toEqual({ detail });
  });
});
