import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiUndoBlueprint: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/blueprint/undo/route";
import { requireOwnedSession } from "@/lib/session-access";
import { apiUndoBlueprint, wizardApiEnabled } from "@/lib/wizard-api-client";

const TRACE = "trace-undo-0001";
const params = { params: Promise.resolve({ id: "s1" }) };

function post(body: unknown, headers: Record<string, string> = {}) {
  const text = JSON.stringify(body);
  return POST(
    new NextRequest("http://localhost/api/sessions/s1/blueprint/undo", {
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(wizardApiEnabled).mockReturnValue(true);
  vi.mocked(requireOwnedSession).mockResolvedValue({ user: { email: "dev@gaik.local" }, session: {} } as never);
});

describe("POST /sessions/[id]/blueprint/undo", () => {
  it("answers 404 for a session that is not the caller's, without asking the api", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);
    expect((await post({ base_version: 3 })).status).toBe(404);
    expect(apiUndoBlueprint).not.toHaveBeenCalled();
  });

  it("answers 503 needs_wizard_api in mock mode", async () => {
    vi.mocked(wizardApiEnabled).mockReturnValue(false);
    const res = await post({ base_version: 3 });
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "needs_wizard_api" });
  });

  it("refuses a body over 64 KB with 413", async () => {
    const res = await post({ base_version: 3 }, { "content-length": String(65 * 1024) });
    expect(res.status).toBe(413);
    expect(apiUndoBlueprint).not.toHaveBeenCalled();
  });

  it("forwards the base version and answers with the session's blueprint and version", async () => {
    vi.mocked(apiUndoBlueprint).mockResolvedValue(
      Response.json({
        id: "s1",
        step: 6,
        gate_statuses: {},
        active_version: 5,
        output_dir: "/srv/wizard/sessions/s1",
        blueprint: { name: "b", steps: [] },
      }),
    );

    const res = await post({ base_version: 4 });

    expect(res.status).toBe(200);
    expect(apiUndoBlueprint).toHaveBeenCalledWith("s1", { base_version: 4 });
    const body = await res.json();
    expect(body).toEqual({ id: "s1", step: 6, gate_statuses: {}, active_version: 5, blueprint: { name: "b", steps: [] } });
  });

  it("answers 502 when a 2xx from wizard_api is not JSON", async () => {
    vi.mocked(apiUndoBlueprint).mockResolvedValue(new Response("not json", { status: 200 }));
    const res = await post({ base_version: 4 });
    expect(res.status).toBe(502);
    expect((await res.json()).detail.error).toBe("upstream_unreachable");
  });

  it.each(["nothing_to_undo", "cannot_undo", "changed_elsewhere", "agent_busy"])(
    "passes a 409 %s through unchanged",
    async (code) => {
      const detail = { error: code, message: "the api's own words", trace_id: TRACE };
      vi.mocked(apiUndoBlueprint).mockResolvedValue(Response.json({ detail }, { status: 409 }));

      const res = await post({ base_version: 4 });

      expect(res.status).toBe(409);
      expect(await res.json()).toEqual({ detail });
    },
  );
});
