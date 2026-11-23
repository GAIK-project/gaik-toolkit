import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// The form's and the flow's save: the owner check, the version it was made
// on, and wizard_api's refusals passed on in their own words, not as a 500.
vi.mock("@/lib/session-access", () => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/sessions", () => ({ patchSessionBlueprint: vi.fn() }));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { PATCH } from "@/app/api/sessions/[id]/blueprint/route";
import { requireOwnedSession } from "@/lib/session-access";
import { patchSessionBlueprint } from "@/lib/sessions";
import { WizardApiError } from "@/lib/wizard-api-client";

const TRACE = "trace-patch-0001";
const params = { params: Promise.resolve({ id: "s1" }) };
const BLUEPRINT = { name: "b", description: "", goal: "", steps: [] };

function patch(body: unknown) {
  return PATCH(
    new NextRequest("http://localhost/api/sessions/s1/blueprint", {
      method: "PATCH",
      headers: { "x-trace-id": TRACE, "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
    params,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(requireOwnedSession).mockResolvedValue({
    user: { email: "dev@gaik.local" },
    session: { id: "s1", blueprint: BLUEPRINT, activeVersion: 4 },
  } as never);
});

describe("PATCH /sessions/[id]/blueprint", () => {
  it("answers 404 for a session that is not the caller's, and saves nothing", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);
    expect((await patch({ content: BLUEPRINT })).status).toBe(404);
    expect(patchSessionBlueprint).not.toHaveBeenCalled();
  });

  it("saves with the version it was made on, and answers with the new version", async () => {
    vi.mocked(patchSessionBlueprint).mockResolvedValue({ blueprint: BLUEPRINT, activeVersion: 5 } as never);

    const res = await patch({ content: BLUEPRINT, note: "n", base_version: 4 });

    expect(res.status).toBe(200);
    expect(patchSessionBlueprint).toHaveBeenCalledWith("s1", BLUEPRINT, "n", 4);
    expect(await res.json()).toEqual({ blueprint: BLUEPRINT, version: 5 });
  });

  it("refuses a save made on an older version than the one the server holds", async () => {
    const res = await patch({ content: BLUEPRINT, base_version: 3 });

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: "changed_elsewhere" });
    expect(patchSessionBlueprint).not.toHaveBeenCalled();
  });

  it("saves without a version when the user chose to write over a newer one", async () => {
    vi.mocked(patchSessionBlueprint).mockResolvedValue({ blueprint: BLUEPRINT, activeVersion: 5 } as never);
    expect((await patch({ content: BLUEPRINT })).status).toBe(200);
    expect(patchSessionBlueprint).toHaveBeenCalledWith("s1", BLUEPRINT, expect.any(String), undefined);
  });

  it.each([
    [409, { error: "changed_elsewhere", message: "The blueprint has changed.", trace_id: TRACE }],
    [409, { error: "agent_busy", message: "The wizard is replying.", trace_id: TRACE }],
    [
      422,
      {
        error: "unsupported_edit",
        message: "This save changes what can only be changed by asking the wizard: steps[0].x",
        fields: ["steps[0].x"],
        trace_id: TRACE,
      },
    ],
  ])("passes wizard_api's %i refusal through unchanged, not as a 500", async (status, detail) => {
    vi.mocked(patchSessionBlueprint).mockRejectedValue(
      new WizardApiError(status, "/sessions/s1/blueprint", JSON.stringify({ detail })),
    );

    const res = await patch({ content: BLUEPRINT, base_version: 4 });

    expect(res.status).toBe(status);
    expect(await res.json()).toEqual({ detail });
  });

  it("keeps a failure that is no refusal a 500", async () => {
    vi.mocked(patchSessionBlueprint).mockResolvedValue(undefined);
    expect((await patch({ content: BLUEPRINT })).status).toBe(500);
  });
});
