import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  apiCreateSession,
  apiDeletePocInput,
  apiGetDeployablePocZip,
  apiListPocInputs,
  apiUploadPocInput,
  apiGetSession,
  apiGetSessionBpmn,
  apiListSessions,
  apiPatchBlueprint,
  apiPatchSession,
  apiPostMessages,
  apiPostVersion,
  apiSyncSessionBpmn,
  getWizardApiUrl,
  openAgentChatStream,
  wizardAgentChatEnabled,
  wizardApiEnabled,
} from "@/lib/wizard-api-client";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("wizardAgentChatEnabled", () => {
  it("is off when the wizard_api URL is not set, even with the flag on", () => {
    vi.stubEnv("WIZARD_API_URL", "");
    vi.stubEnv("WIZARD_AGENT_CHAT", "true");
    expect(wizardApiEnabled()).toBe(false);
    expect(wizardAgentChatEnabled()).toBe(false);
  });

  it("is off when the API is set but the agent flag is not 'true'", () => {
    vi.stubEnv("WIZARD_API_URL", "http://localhost:8100");
    vi.stubEnv("WIZARD_AGENT_CHAT", "");
    expect(wizardApiEnabled()).toBe(true);
    expect(wizardAgentChatEnabled()).toBe(false);
  });

  it("is on only when the API is set and the flag is exactly 'true'", () => {
    vi.stubEnv("WIZARD_API_URL", "http://localhost:8100");
    vi.stubEnv("WIZARD_AGENT_CHAT", "true");
    expect(wizardAgentChatEnabled()).toBe(true);
  });
});

describe("getWizardApiUrl", () => {
  it("trims whitespace and returns null for an empty value", () => {
    vi.stubEnv("WIZARD_API_URL", "  ");
    expect(getWizardApiUrl()).toBeNull();
  });

  it("returns the trimmed URL when set", () => {
    vi.stubEnv("WIZARD_API_URL", "  http://localhost:8100  ");
    expect(getWizardApiUrl()).toBe("http://localhost:8100");
  });
});

describe("wizardFetch-backed API helpers", () => {
  const detail = {
    id: "s1",
    user_id: "u1",
    title: "Demo",
    step: 1,
    status: "active",
    gate_statuses: {},
    metadata: {},
    output_dir: "output/s1/",
    active_version: 1,
    versions: [],
    blueprint: { name: "Demo", description: "", goal: "", steps: [] },
    messages: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };

  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.stubEnv("WIZARD_API_URL", "http://api.test");
    fetchMock = vi.fn(async () => new Response(JSON.stringify(detail), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  it("apiCreateSession POSTs to /sessions with user_id and title", async () => {
    await apiCreateSession("u1", "Demo");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/sessions",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ user_id: "u1", title: "Demo" });
  });

  it("apiListSessions GETs /sessions?user_id=... and unwraps the sessions array", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ sessions: [detail] }), { status: 200 }),
    );
    const sessions = await apiListSessions("u1");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/sessions?user_id=u1",
      expect.anything(),
    );
    expect(sessions).toEqual([detail]);
  });

  it("apiGetSession GETs /sessions/{id}", async () => {
    await apiGetSession("s1");
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/sessions/s1", expect.anything());
  });

  it("apiPatchSession PATCHes with only the given fields", async () => {
    await apiPatchSession("s1", { step: 3 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/sessions/s1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ step: 3 });
  });

  it("apiPostMessages POSTs user/assistant content to /sessions/{id}/messages", async () => {
    await apiPostMessages("s1", "hi", "hello");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/sessions/s1/messages");
    expect(JSON.parse(init.body)).toEqual({
      user_content: "hi",
      assistant_content: "hello",
    });
  });

  it("apiPostVersion POSTs a note (and optional content) to /sessions/{id}/versions", async () => {
    await apiPostVersion("s1", "checkpoint");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ note: "checkpoint", content: undefined });
  });

  it("apiPatchBlueprint PATCHes content + note to /sessions/{id}/blueprint", async () => {
    await apiPatchBlueprint("s1", detail.blueprint, "edited");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/sessions/s1/blueprint");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ content: detail.blueprint, note: "edited" });
  });

  it("apiGetSessionBpmn returns the raw XML text", async () => {
    fetchMock.mockResolvedValueOnce(new Response("<bpmn/>", { status: 200 }));
    const xml = await apiGetSessionBpmn("s1");
    expect(xml).toBe("<bpmn/>");
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/sessions/s1/bpmn", expect.anything());
  });

  it("apiGetSessionBpmn throws with status + body text on failure", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));
    await expect(apiGetSessionBpmn("s1")).rejects.toThrow(/500/);
  });

  it("apiSyncSessionBpmn POSTs the xml to /sessions/{id}/bpmn/sync", async () => {
    await apiSyncSessionBpmn("s1", "<bpmn/>");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/sessions/s1/bpmn/sync");
    expect(JSON.parse(init.body)).toEqual({ xml: "<bpmn/>" });
  });

  it("throws a descriptive error when the upstream response is not ok", async () => {
    fetchMock.mockResolvedValueOnce(new Response("nope", { status: 404 }));
    await expect(apiGetSession("s1")).rejects.toThrow(/wizard_api 404/);
  });

  it("falls back to the default API URL when WIZARD_API_URL is unset", async () => {
    vi.unstubAllEnvs();
    await apiGetSession("s1");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8100/sessions/s1",
      expect.anything(),
    );
  });
});

describe("openAgentChatStream", () => {
  it("POSTs the message as an SSE request and includes locale when given", async () => {
    vi.stubEnv("WIZARD_API_URL", "http://api.test");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await openAgentChatStream("s1", "hello", "en");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }];
    expect(url).toBe("http://api.test/sessions/s1/chat");
    expect(init.method).toBe("POST");
    expect(init.headers.Accept).toBe("text/event-stream");
    expect(JSON.parse(init.body as string)).toEqual({ message: "hello", locale: "en" });
  });

  it("omits locale from the body when not given", async () => {
    vi.stubEnv("WIZARD_API_URL", "http://api.test");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await openAgentChatStream("s1", "hello");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ message: "hello" });
  });
});

// --- Service token (#132) ---------------------------------------------------
//
// Asserted through the real call sites rather than against outgoingHeaders()
// directly: the point of the ticket is that EVERY outgoing call carries the
// token, and there are three separate fetch call sites in this module that
// could each forget it.

describe("service token on outgoing calls (#132)", () => {
  const TOKEN_HEADER = "X-Wizard-Service-Token";
  let fetchMock: ReturnType<typeof vi.fn>;

  const headersOfCall = (i: number) =>
    (fetchMock.mock.calls[i] as [string, RequestInit & { headers: Record<string, string> }])[1]
      .headers;

  beforeEach(() => {
    vi.stubEnv("WIZARD_API_URL", "http://api.test");
    fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  it("sends the token on plain JSON calls", async () => {
    vi.stubEnv("WIZARD_API_TOKEN", "s3cret");
    await apiListSessions("u1");
    expect(headersOfCall(0)[TOKEN_HEADER]).toBe("s3cret");
  });

  it("sends the token on the agent chat stream", async () => {
    vi.stubEnv("WIZARD_API_TOKEN", "s3cret");
    await openAgentChatStream("s1", "hello");
    expect(headersOfCall(0)[TOKEN_HEADER]).toBe("s3cret");
  });

  it("sends the token on the raw BPMN fetch", async () => {
    vi.stubEnv("WIZARD_API_TOKEN", "s3cret");
    await apiGetSessionBpmn("s1");
    expect(headersOfCall(0)[TOKEN_HEADER]).toBe("s3cret");
  });

  it("omits the header when no token is configured, so local dev still works", async () => {
    vi.stubEnv("WIZARD_API_TOKEN", "");
    await apiListSessions("u1");
    expect(TOKEN_HEADER in headersOfCall(0)).toBe(false);
  });

  it("treats a whitespace-only token as unset", async () => {
    vi.stubEnv("WIZARD_API_TOKEN", "   ");
    await apiListSessions("u1");
    expect(TOKEN_HEADER in headersOfCall(0)).toBe(false);
  });
});


// --- User header (#134) -------------------------------------------------------

describe("user header on outgoing calls (#134)", () => {
  const USER_HEADER = "X-Wizard-User-Id";
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    process.env.WIZARD_API_URL = "http://api.test";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.doUnmock("@/lib/current-user");
    delete process.env.WIZARD_API_URL;
  });

  it("names the signed-in user by owner id so wizard_api can refuse another user's session", async () => {
    vi.doMock("@/lib/current-user", () => ({
      getCurrentUser: vi.fn(async () => ({ email: "alice@example.com" })),
    }));
    const { apiListSessions } = await import("@/lib/wizard-api-client");
    await apiListSessions("alice@example.com");
    const headers = (fetchMock.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }])[1]
      .headers;
    const { ownerId } = await import("@/lib/owner-id");
    expect(headers[USER_HEADER]).toBe(ownerId("alice@example.com"));
    expect(headers[USER_HEADER]).toMatch(/^o_[0-9a-f]{32}$/);
  });

  it("sends no user header where there is no signed-in user", async () => {
    vi.doMock("@/lib/current-user", () => ({
      getCurrentUser: vi.fn(async () => null),
    }));
    const { apiListSessions } = await import("@/lib/wizard-api-client");
    await apiListSessions("alice@example.com");
    const headers = (fetchMock.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }])[1]
      .headers;
    expect(headers[USER_HEADER]).toBeUndefined();
  });
});

describe("sample input and the deployable package (#95, #143)", () => {
  beforeEach(() => {
    vi.stubEnv("WIZARD_API_URL", "http://api.test");
    vi.stubEnv("WIZARD_API_TOKEN", "svc-token");
  });

  it("lists the package's sample input files", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify({ files: [{ name: "a.pdf", bytes: 3 }] })));
    vi.stubGlobal("fetch", fetchMock);
    const out = await apiListPocInputs("s1");
    expect(out.files).toEqual([{ name: "a.pdf", bytes: 3 }]);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/sessions/s1/poc/input");
  });

  it("uploads one file as multipart with the service token and no fixed content type", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array([1, 2, 3])]), "a.pdf");
    const res = await apiUploadPocInput("s1", form);
    expect(res.status).toBe(201);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }];
    expect(url).toBe("http://api.test/sessions/s1/poc/input");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(form);
    expect(init.headers["X-Wizard-Service-Token"]).toBe("svc-token");
    expect(Object.keys(init.headers).map((k) => k.toLowerCase())).not.toContain("content-type");
  });

  it("deletes a file by its encoded name", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await apiDeletePocInput("s1", "lasku 1.pdf");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/sessions/s1/poc/input/lasku%201.pdf");
    expect(init.method).toBe("DELETE");
  });

  it("fetches the deployable zip from its own endpoint, not the development zip", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("zip", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await apiGetDeployablePocZip("s1");
    expect(res.ok).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/sessions/s1/poc/deployable");
  });
});
