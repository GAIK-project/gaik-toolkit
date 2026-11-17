import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// The route's collaborators are mocked so the test exercises only the routing
// logic: the owner check, the scripted reply without wizard_api, and what
// wizard_api's answers become.
vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(),
}));
vi.mock("@/lib/mock-sessions", () => ({
  stopMockReply: vi.fn(() => false),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardAgentChatEnabled: vi.fn(() => false),
  stopAgentChat: vi.fn(),
}));

import { POST } from "@/app/api/sessions/[id]/chat/stop/route";
import { requireOwnedSession } from "@/lib/session-access";
import { stopMockReply } from "@/lib/mock-sessions";
import { stopAgentChat, wizardAgentChatEnabled } from "@/lib/wizard-api-client";

function post() {
  const req = new NextRequest("http://localhost/api/sessions/s1/chat/stop", { method: "POST" });
  return POST(req, { params: Promise.resolve({ id: "s1" }) });
}

beforeEach(() => {
  vi.mocked(requireOwnedSession).mockResolvedValue({
    user: { email: "dev@gaik.local" },
    session: { id: "s1", step: 2 },
  } as never);
  vi.mocked(wizardAgentChatEnabled).mockReturnValue(false);
  vi.mocked(stopMockReply).mockReturnValue(false);
});

afterEach(() => vi.clearAllMocks());

describe("POST /sessions/[id]/chat/stop", () => {
  it("answers 404 for a session that is not the signed-in user's, and stops nothing", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);

    const res = await post();

    expect(res.status).toBe(404);
    expect(stopAgentChat).not.toHaveBeenCalled();
    expect(stopMockReply).not.toHaveBeenCalled();
  });

  it("stops the scripted reply when wizard_api is not in play", async () => {
    vi.mocked(stopMockReply).mockReturnValue(true);

    const res = await post();

    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ stopping: true });
    expect(stopMockReply).toHaveBeenCalledWith("s1");
    expect(stopAgentChat).not.toHaveBeenCalled();
  });

  it("answers 409 when no scripted reply is being written", async () => {
    const res = await post();

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: "no_reply_running" });
  });

  it("passes the stop on to wizard_api", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(stopAgentChat).mockResolvedValue(
      new Response(JSON.stringify({ stopping: true }), { status: 202 }),
    );

    const res = await post();

    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ stopping: true });
    expect(stopAgentChat).toHaveBeenCalledWith("s1");
    expect(stopMockReply).not.toHaveBeenCalled();
  });

  it("answers 409 when wizard_api has no reply running, in the relay's own words", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(stopAgentChat).mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { error: "no_reply_running", message: "x", trace_id: "t" } }),
        { status: 409 },
      ),
    );

    const res = await post();

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: "no_reply_running" });
  });

  it("answers 502 for any other answer, without its body", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(stopAgentChat).mockResolvedValue(new Response("Traceback …", { status: 500 }));

    const res = await post();

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "upstream", status: 500 });
  });

  it("answers 502 when wizard_api cannot be reached", async () => {
    vi.mocked(wizardAgentChatEnabled).mockReturnValue(true);
    vi.mocked(stopAgentChat).mockRejectedValue(new Error("connect ECONNREFUSED"));

    const res = await post();

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "upstream" });
  });
});
