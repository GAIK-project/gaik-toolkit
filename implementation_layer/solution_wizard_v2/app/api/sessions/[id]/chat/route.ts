// SSE streaming endpoint for the mock chat reply.
// Streams the reply as text/event-stream, token by token. Mock: the reply is
// phase-aware and in the user's language (i18n cookie).

import { NextRequest } from "next/server";
import { getI18n } from "@/lib/i18n";
import { requireOwnedSession } from "@/lib/session-access";
import { postMessage } from "@/lib/sessions";
import { resolveChatReply, toStreamTokens } from "@/lib/chat-driver";
import {
  openAgentChatStream,
  wizardAgentChatEnabled,
} from "@/lib/wizard-api-client";
import { withLogging } from "@/lib/with-logging";
import { chatMessageTooLong } from "@/lib/chat-limits";
import { STOPPED_NOTE, withStoppedNote } from "@/lib/chat-stopped";
import { beginMockReply, endMockReply, mockReplyPace } from "@/lib/mock-sessions";
import { setContextUserId, getTraceId } from "@/lib/request-context";
import { logger } from "@/lib/logger";

export const dynamic = "force-dynamic";

const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
} as const;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function sse(data: unknown): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(data)}\n\n`);
}

export const POST = withLogging("chat.post", async (
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) => {
  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const userMessage = ((body?.message as string) ?? "").trim();

  if (!userMessage) {
    return new Response("Empty message", { status: 400 });
  }
  if (chatMessageTooLong(userMessage)) {
    return new Response("Message too long", { status: 413 });
  }

  const owned = await requireOwnedSession(id);
  if (!owned) {
    return new Response("Session not found", { status: 404 });
  }
  setContextUserId(owned.user.email);

  // Read the locale before the agent call, not after it: it is what pins the
  // agent's reply language. The whole chain already existed — the client sends
  // it, wizard_api accepts it, the bootstrap prompt uses it — and this call was
  // the one place that never passed it, so the agent chose its own language.
  const { locale, t } = await getI18n();

  // When the wizard_api agent chat endpoint (#29 backend) is live, proxy the
  // message to it and stream the reply straight through. wizard_api persists the
  // exchange. A failure is a failure: it used to fall through to the mock reply
  // below, which was then stored in the transcript as the wizard's answer. The
  // mock is for local dev without wizard_api only.
  if (wizardAgentChatEnabled()) {
    const json = { "Content-Type": "application/json" };
    try {
      const upstream = await openAgentChatStream(id, userMessage, locale);
      if (upstream.ok && upstream.body) {
        return new Response(upstream.body, { headers: SSE_HEADERS });
      }
      if (upstream.status === 409) {
        // The agent is still answering the previous message (#173 wake-up).
        return new Response(JSON.stringify({ error: "busy" }), { status: 409, headers: json });
      }
      if (upstream.status === 429) {
        // This user's own agents are all busy (agent_busy), or they are over the
        // per-minute message limit (chat_rate_limited). Retry-After goes along.
        const upstreamBody = await upstream.json().catch(() => ({}));
        const error =
          upstreamBody?.detail?.error === "chat_rate_limited" ? "rate_limited" : "agent_busy";
        const retryAfter = upstream.headers.get("Retry-After");
        return new Response(JSON.stringify({ error }), {
          status: 429,
          headers: retryAfter ? { ...json, "Retry-After": retryAfter } : json,
        });
      }
      if (upstream.status === 402) {
        // A usage cap is reached: whose it is (session, user, deployment) picks
        // the chat's message. Only a known scope is passed on.
        const upstreamBody = await upstream.json().catch(() => ({}));
        const scope = upstreamBody?.detail?.scope;
        return new Response(
          JSON.stringify({
            error: "usage_cap",
            scope: scope === "user" || scope === "deployment" ? scope : "session",
          }),
          { status: 402, headers: json },
        );
      }
      if (upstream.status === 413 || upstream.status === 503) {
        // Too long, or no free agent slot: the chat says which, and the gate
        // wake-up waits for a slot as it does for a busy agent.
        const error = upstream.status === 413 ? "too_long" : "capacity";
        return new Response(JSON.stringify({ error }), { status: upstream.status, headers: json });
      }
      logger.error(
        { traceId: getTraceId(), sessionId: id, status: upstream.status },
        "chat.post agent upstream returned non-ok",
      );
      return new Response(JSON.stringify({ error: "upstream", status: upstream.status }), {
        status: 502,
        headers: json,
      });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "chat.post agent upstream threw");
      return new Response(JSON.stringify({ error: "upstream" }), { status: 502, headers: json });
    }
  }

  // Local dev without wizard_api: a scripted reply so the UI can be exercised.
  const fullReply = await resolveChatReply(id, owned.session, userMessage, t);
  const tokens = toStreamTokens(fullReply);

  // The stop route reaches the reply through this handle (lib/mock-sessions).
  const reply = beginMockReply(id);
  const stream = new ReadableStream({
    async start(controller) {
      try {
        let written = "";
        for (const token of tokens) {
          if (req.signal.aborted) {
            controller.close();
            return;
          }
          if (reply.stopped) {
            // Stopped by the user: what was written so far is the reply, stored
            // as wizard_api stores a stopped one.
            const note = STOPPED_NOTE[locale];
            await postMessage(id, userMessage, withStoppedNote(written, note), note);
            controller.enqueue(sse({ stopped: true, tool: null }));
            controller.close();
            return;
          }
          controller.enqueue(sse({ delta: token }));
          written += token;
          await sleep(mockReplyPace());
        }
        // Persist the conversation so a reload shows the complete message.
        await postMessage(id, userMessage, fullReply);
        controller.enqueue(sse({ done: true }));
        controller.close();
      } catch (err) {
        logger.error(
          { traceId: getTraceId(), err, sessionId: id },
          "chat.post reply stream failed",
        );
        controller.enqueue(sse({ error: true }));
        controller.close();
      } finally {
        endMockReply(id, reply);
      }
    },
  });

  return new Response(stream, { headers: SSE_HEADERS });
});
