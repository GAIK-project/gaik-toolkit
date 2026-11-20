import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// The route's collaborators are mocked so the test exercises only the routing
// logic: mock reply by default, proxy to wizard_api when the agent is enabled,
// and an upstream failure reported as one (never a mock reply in the transcript).
vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(),
}));
vi.mock("@/lib/i18n", () => ({
  getI18n: vi.fn(async () => ({ locale: "fi", t: {} })),
}));
vi.mock("@/lib/sessions", () => ({
  postMessage: vi.fn(async () => undefined),
}));
vi.mock("@/lib/chat-driver", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/chat-driver")>(
      "@/lib/chat-driver",
    );
  return { ...actual, resolveChatReply: vi.fn(async () => "MOCK") };
});
vi.mock("@/lib/wizard-api-client", () => ({
  wizardAgentChatEnabled: vi.fn(() => false),
  openAgentChatStream: vi.fn(),
}));

import { POST } from "@/app/api/sessions/[id]/chat/route";
import { requireOwnedSession } from "@/lib/session-access";
import { resolveChatReply } from "@/lib/chat-driver";
import { postMessage } from "@/lib/sessions";
import { resetMockSessions, setMockReplyPace, stopMockReply } from "@/lib/mock-sessions";
import {
  openAgentChatStream,
  wizardAgentChatEnabled,
} from "@/lib/wizard-api-client";

function post(message = "hi") {
  const req = new NextRequest("http://localhost/api/sessions/s1/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  return POST(req, { params: Promise.resolve({ id: "s1" }) });
}

async function readAll(res: Response): Promise<string> {
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let out = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out += dec.decode(value, { stream: true });
  }
  return out;
}

function upstreamSse(...frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      const enc = new TextEncoder();
      for (const f of frames) c.enqueue(enc.encode(`data: ${f}\n\n`));
      c.close();
    },
  });
  return new Response(body, { status: 200 });
}

beforeEach(() => {
  vi.mocked(requireOwnedSession).mockResolvedValue({
    user: { email: "dev@gaik.local" },
    session: { id: "s1", step: 2 },
  } as never);
  vi.mocked(resolveChatReply).mockResolvedValue("MOCK");
  vi.mocked(wizardAgentChatEnabled).mockReturnValue(false);
});

afterEach(() => vi.clearAllMocks());

describe("POST /sessions/[id]/chat", () => {
  it("returns 400 on an empty message", async () => {
    const res = await post("   ");
    expect(res.status).toBe(400);
  });

  it("streams the mock reply when the agent is disabled", async () => {
    const res = await post();
    expect(res.headers.get("Content-Type")).toContain("text/event-stream");
    const body = await readAll(res);
    expect(body).toContain('"delta"');
    expect(body).toContain("MOCK");
    expect(body).toContain('"done":true');
    expect(openAgentChatStream).not.toHaveBeenCalled();
  });

  it("stops the scripted reply where it is and stores what was written as stopped", async () => {
    vi.mocked(resolveChatReply).mockResolvedValue("one two three four five six seven eight nine ten");
    setMockReplyPace(40);
    try {
      const res = await post();
      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      // The first word is on its way to the page: the user presses Stop.
      let body = dec.decode((await reader.read()).value, { stream: true });
      expect(stopMockReply("s1")).toBe(true);
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        body += dec.decode(value, { stream: true });
      }

      expect(body).toContain('"stopped":true');
      expect(body).not.toContain('"done":true');
      expect(body).not.toContain("ten");
      const [id, user, stored, note] = vi.mocked(postMessage).mock.calls[0];
      expect([id, user, note]).toEqual(["s1", "hi", "(Pysäytetty)"]);
      expect(stored).toMatch(/^one( two)?( three)?\n\n\(Pysäytetty\)$/);
      // The reply is over: there is nothing left to stop.
      expect(stopMockReply("s1")).toBe(false);
    } finally {
      resetMockSessions();
    }
  });

  it("proxies the upstream agent stream when enabled", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(
      upstreamSse('{"delta":"AGENT"}', '{"done":true}'),
    );
    const res = await post();
    const body = await readAll(res);
    expect(body).toContain("AGENT");
    // The mock path must not run when the proxy handled the request.
    expect(resolveChatReply).not.toHaveBeenCalled();
  });

  it("answers 502 when the upstream throws, never a mock reply", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockRejectedValue(
      new Error("connect ECONNREFUSED"),
    );
    const res = await post();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "upstream" });
    expect(resolveChatReply).not.toHaveBeenCalled();
  });

  it("answers 502 with the upstream status when the upstream is not ok", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(
      new Response("nope", { status: 500 }),
    );
    const res = await post();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "upstream", status: 500 });
    expect(resolveChatReply).not.toHaveBeenCalled();
  });

  it.each([
    ["agent_busy", "agent_busy", "30"],
    ["chat_rate_limited", "rate_limited", "12"],
  ])("passes a 429 %s on as %s with its Retry-After", async (upstreamCode, code, retryAfter) => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(
      new Response(JSON.stringify({ detail: { error: upstreamCode, message: "x" } }), {
        status: 429,
        headers: { "Retry-After": retryAfter },
      }),
    );
    const res = await post();
    expect(res.status).toBe(429);
    expect(res.headers.get("Retry-After")).toBe(retryAfter);
    expect(await res.json()).toEqual({ error: code });
    expect(resolveChatReply).not.toHaveBeenCalled();
  });

  it.each([
    ["session", "session"],
    ["user", "user"],
    ["deployment", "deployment"],
    ["<b>other</b>", "session"],
  ])("passes a 402 usage cap of scope %s on as %s", async (upstreamScope, scope) => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { error: "usage_cap", message: "x", scope: upstreamScope } }),
        { status: 402 },
      ),
    );
    const res = await post();
    expect(res.status).toBe(402);
    expect(await res.json()).toEqual({ error: "usage_cap", scope });
    expect(resolveChatReply).not.toHaveBeenCalled();
  });

  it("passes a 402 whose body is not JSON on as the session's cap", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(new Response("Payment Required", { status: 402 }));
    const res = await post();
    expect(res.status).toBe(402);
    expect(await res.json()).toEqual({ error: "usage_cap", scope: "session" });
  });

  it("answers 409 while the agent is still responding", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(
      new Response("The wizard is still responding.", { status: 409 }),
    );
    const res = await post();
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: "busy" });
    expect(resolveChatReply).not.toHaveBeenCalled();
  });
});

describe("POST /sessions/[id]/chat — reply language", () => {
  it("passes the UI locale to the agent", async () => {
    // T5 / 17: the client, wizard_api and the bootstrap prompt all handled the
    // locale; this route was the one place that never sent one, so the agent
    // picked its own language and once answered in Italian.
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(openAgentChatStream).mockResolvedValue(
      upstreamSse('{"done":true}'),
    );

    await post("hei");

    expect(openAgentChatStream).toHaveBeenCalledWith("s1", "hei", "fi");
  });
});
