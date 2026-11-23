import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const state = vi.hoisted(() => ({
  user: { email: "alice@example.test" } as { email: string } | null,
  createSession: vi.fn(),
  audit: vi.fn(),
}));

vi.mock("@/lib/current-user", () => ({ getCurrentUser: async () => state.user }));
vi.mock("@/lib/sessions", () => ({ createSession: state.createSession }));
vi.mock("@/lib/audit", () => ({ audit: state.audit }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "fi", t: actual.dictionary("fi") }) };
});

import { POST } from "@/app/api/sessions/route";
import { dictionary } from "@/lib/i18n";
import { WizardApiError } from "@/lib/wizard-api-client";

function post(body: unknown) {
  const req = new NextRequest("http://localhost/api/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
  return POST(req);
}

beforeEach(() => {
  vi.clearAllMocks();
  state.user = { email: "alice@example.test" };
  state.createSession.mockResolvedValue({ id: "ses_new" });
});

describe("POST /api/sessions", () => {
  it("without a signed-in user answers 401 and creates nothing", async () => {
    state.user = null;
    const res = await post({ title: "Laskujen luokittelu" });
    expect(res.status).toBe(401);
    expect(state.createSession).not.toHaveBeenCalled();
    expect(state.audit).not.toHaveBeenCalled();
  });

  it("creates the signed-in user's session with the given name", async () => {
    const res = await post({ title: "  Laskujen luokittelu  " });
    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ id: "ses_new" });
    // The owner is the signed-in user, never one the request names.
    expect(state.createSession).toHaveBeenCalledTimes(1);
    expect(state.createSession).toHaveBeenCalledWith("alice@example.test", "Laskujen luokittelu");
    expect(state.audit).toHaveBeenCalledWith(
      "session.create",
      expect.objectContaining({ actor: "alice@example.test", outcome: "success" }),
    );
  });

  it("names a session started without a name in the interface's language", async () => {
    for (const body of [{}, { title: "   " }, "not json"]) {
      state.createSession.mockClear();
      const res = await post(body);
      expect(res.status).toBe(201);
      expect(state.createSession).toHaveBeenCalledWith(
        "alice@example.test",
        dictionary("fi").untitledSession,
      );
    }
  });

  it("refuses a name that is not text or is longer than 255 characters", async () => {
    for (const title of [42, null, ["a"], "a".repeat(256)]) {
      const res = await post({ title });
      expect(res.status, JSON.stringify(title).slice(0, 20)).toBe(400);
      expect(await res.json()).toEqual({ error: "invalid_title" });
    }
    expect(state.createSession).not.toHaveBeenCalled();
    // The longest name that is allowed.
    expect((await post({ title: "a".repeat(255) })).status).toBe(201);
  });

  it("answers 429 session_limit when the account has all the sessions it may have", async () => {
    state.createSession.mockRejectedValue(
      new WizardApiError(
        429,
        "/sessions",
        JSON.stringify({ detail: { error: "session_limit", message: "x" } }),
      ),
    );
    const res = await post({ title: "Laskujen luokittelu" });
    expect(res.status).toBe(429);
    expect(await res.json()).toEqual({ error: "session_limit" });
    expect(state.audit).toHaveBeenCalledWith(
      "session.create",
      expect.objectContaining({ actor: "alice@example.test", outcome: "denied" }),
    );
  });

  it("answers 502 when the session could not be created, without the cause", async () => {
    state.createSession.mockRejectedValue(new Error("wizard_api 500: connection refused"));
    const res = await post({ title: "Laskujen luokittelu" });
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "failed" });
    expect(state.audit).toHaveBeenCalledWith(
      "session.create",
      expect.objectContaining({ actor: "alice@example.test", outcome: "error" }),
    );
  });
});
