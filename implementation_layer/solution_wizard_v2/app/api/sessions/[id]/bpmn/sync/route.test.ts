import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// Collaborators are mocked so the test exercises the route's own decisions:
// the size cap before anything is spawned, and that a normal document still
// reaches the linter and the sync.
vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({
    user: { email: "dev@gaik.local" },
    session: { step: 10, blueprint: { name: "b", steps: [] }, activeVersion: 4 },
  })),
}));
vi.mock("@/lib/bpmn-spike", () => ({
  BPMN_VISUAL_STEP: 5,
  hasBpmnSpike: vi.fn(() => true),
}));
vi.mock("@/lib/bpmn-lint", () => ({
  BPMN_XML_MAX_BYTES: 1024,
  BpmnLintBusyError: class BpmnLintBusyError extends Error {},
  lintBpmnXml: vi.fn(async () => ({ ok: true, errors: [], warnings: [], issues: [] })),
}));
vi.mock("@/lib/bpmn-generate", () => ({
  syncSessionBpmn: vi.fn(async (_id: string, blueprint: unknown, xml: string) => ({
    blueprint,
    xml,
  })),
}));
vi.mock("@/lib/sessions", () => ({
  saveBlueprintAfterBpmnSync: vi.fn(async () => undefined),
}));
const apiState = vi.hoisted(() => ({ enabled: false }));
vi.mock("@/lib/wizard-api-client", async (original) => ({
  // The real error class: wizard_api's refusals reach the route as it.
  WizardApiError: (await original<typeof import("@/lib/wizard-api-client")>()).WizardApiError,
  wizardApiEnabled: () => apiState.enabled,
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/bpmn/sync/route";
import { lintBpmnXml } from "@/lib/bpmn-lint";
import { syncSessionBpmn } from "@/lib/bpmn-generate";
import { saveBlueprintAfterBpmnSync } from "@/lib/sessions";
import { WizardApiError } from "@/lib/wizard-api-client";

const TRACE = "trace-sync-0001";

function post(xml: string, headers: Record<string, string> = {}, query = "", extra: Record<string, unknown> = {}) {
  const body = JSON.stringify({ xml, ...extra });
  // A browser's fetch always says the length of a string body.
  const req = new NextRequest(`http://localhost/api/sessions/s1/bpmn/sync${query}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(body, "utf8")),
      "x-trace-id": TRACE,
      ...headers,
    },
    body,
  });
  return POST(req, { params: Promise.resolve({ id: "s1" }) });
}

beforeEach(() => {
  vi.clearAllMocks();
  apiState.enabled = false;
});

describe("POST /sessions/[id]/bpmn/sync — one save, one version", () => {
  it("leaves the version to wizard_api, which stores it in /bpmn/sync", async () => {
    // A second PATCH /blueprint after the sync wrote an identical version, so
    // every diagram save added two to the version count.
    apiState.enabled = true;
    const res = await post("<bpmn:definitions/>");
    expect(res.status).toBe(200);
    expect(syncSessionBpmn).toHaveBeenCalledTimes(1);
    expect(saveBlueprintAfterBpmnSync).not.toHaveBeenCalled();
  });

  it("saves the synced blueprint once in mock mode, where the sync stores nothing", async () => {
    const res = await post("<bpmn:definitions/>");
    expect(res.status).toBe(200);
    expect(saveBlueprintAfterBpmnSync).toHaveBeenCalledTimes(1);
    expect(saveBlueprintAfterBpmnSync).toHaveBeenCalledWith("s1", { name: "b", steps: [] });
  });
});

describe("POST /sessions/[id]/bpmn/sync — size cap (T3)", () => {
  it("refuses a document over the limit before the linter is spawned", async () => {
    const res = await post("<bpmn>" + "x".repeat(2000) + "</bpmn>");
    expect(res.status).toBe(413);
    expect(await res.text()).toMatch(/too large/);
    expect(lintBpmnXml).not.toHaveBeenCalled();
    expect(syncSessionBpmn).not.toHaveBeenCalled();
  });

  it("refuses on the declared content length alone, without reading the body", async () => {
    const res = await post("<bpmn/>", { "content-length": String(10 * 1024 * 1024) });
    expect(res.status).toBe(413);
    expect(lintBpmnXml).not.toHaveBeenCalled();
  });

  it("refuses a body that does not say its length, before reading it", async () => {
    const req = new NextRequest("http://localhost/api/sessions/s1/bpmn/sync", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ xml: "<bpmn/>" }),
    });
    const res = await POST(req, { params: Promise.resolve({ id: "s1" }) });
    expect(res.status).toBe(411);
    expect(lintBpmnXml).not.toHaveBeenCalled();
  });

  it("lints and syncs a document within the limit", async () => {
    const res = await post("<bpmn:definitions/>");
    expect(res.status).toBe(200);
    expect(lintBpmnXml).toHaveBeenCalledTimes(1);
    expect(syncSessionBpmn).toHaveBeenCalledTimes(1);
    const body = (await res.json()) as { lint: { ok: boolean } };
    expect(body.lint.ok).toBe(true);
  });

  it("returns the diagram drawn as it was shown, with or without data objects", async () => {
    await post("<bpmn:definitions/>");
    expect(vi.mocked(syncSessionBpmn).mock.calls[0][3]).toEqual({ dataObjects: true });
    await post("<bpmn:definitions/>", {}, "?data_objects=0");
    expect(vi.mocked(syncSessionBpmn).mock.calls[1][3]).toEqual({ dataObjects: false });
  });

  it("refuses a data_objects value other than 0 or 1 before linting", async () => {
    const res = await post("<bpmn:definitions/>", {}, "?data_objects=2");
    expect(res.status).toBe(400);
    expect(lintBpmnXml).not.toHaveBeenCalled();
    expect(syncSessionBpmn).not.toHaveBeenCalled();
  });

  it("asks to retry, and saves nothing, when the linter is busy", async () => {
    const { BpmnLintBusyError } = await import("@/lib/bpmn-lint");
    vi.mocked(lintBpmnXml).mockRejectedValueOnce(new BpmnLintBusyError());
    const res = await post("<bpmn:definitions/>");
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("2");
    expect(syncSessionBpmn).not.toHaveBeenCalled();
  });
});

describe("POST /sessions/[id]/bpmn/sync — refusals", () => {
  it("refuses a canvas drawn from an older version than the one the server holds", async () => {
    const res = await post("<bpmn:definitions/>", {}, "", { base_version: 3 });
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: "changed_elsewhere" });
    expect(syncSessionBpmn).not.toHaveBeenCalled();
  });

  it("syncs a canvas drawn from the version the server holds", async () => {
    const res = await post("<bpmn:definitions/>", {}, "", { base_version: 4 });
    expect(res.status).toBe(200);
    expect(syncSessionBpmn).toHaveBeenCalledTimes(1);
  });

  it.each([
    [422, { error: "unsupported_edit", message: "Ask the wizard: Task_x", fields: ["Task_x"], trace_id: TRACE }],
    [409, { error: "agent_busy", message: "The wizard is replying.", trace_id: TRACE }],
    [409, { error: "changed_elsewhere", message: "The blueprint has changed.", trace_id: TRACE }],
  ])("passes wizard_api's %i refusal through unchanged, not as a 500", async (status, detail) => {
    apiState.enabled = true;
    vi.mocked(syncSessionBpmn).mockRejectedValueOnce(
      new WizardApiError(status, "/sessions/s1/bpmn/sync", JSON.stringify({ detail })),
    );

    const res = await post("<bpmn:definitions/>");

    expect(res.status).toBe(status);
    expect(await res.json()).toEqual({ detail });
  });

  it("keeps any other failure a 500, without its text", async () => {
    vi.mocked(syncSessionBpmn).mockRejectedValueOnce(
      new WizardApiError(500, "/sessions/s1/bpmn/sync", "Traceback /srv/x"),
    );
    const res = await post("<bpmn:definitions/>");
    expect(res.status).toBe(500);
    expect(await res.text()).not.toContain("/srv/x");
  });
});

describe("POST /sessions/[id]/bpmn/sync — the version the save wrote", () => {
  it("answers with wizard_api's new version, the base of the canvas's next save", async () => {
    apiState.enabled = true;
    vi.mocked(syncSessionBpmn).mockResolvedValueOnce({ blueprint: { name: "b", steps: [] } as never, xml: "<x/>", version: 5 });
    const res = await post("<bpmn:definitions/>");
    expect(((await res.json()) as { version?: number }).version).toBe(5);
  });

  it("answers with the mock store's new version in mock mode", async () => {
    vi.mocked(saveBlueprintAfterBpmnSync).mockResolvedValueOnce({ activeVersion: 6 } as never);
    const res = await post("<bpmn:definitions/>");
    expect(((await res.json()) as { version?: number }).version).toBe(6);
  });
});
