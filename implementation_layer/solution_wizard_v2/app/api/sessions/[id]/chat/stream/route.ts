// Joins the reply that is on its way for a session.
//
// A chat turn runs in wizard_api as its own task, so a page that reloads (or
// opens in another tab) mid-reply can read the reply from its first frame
// here instead of losing it. 204 when no turn is running: the stored
// conversation then has everything.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { openRunningChatStream, wizardAgentChatEnabled } from "@/lib/wizard-api-client";
import { withLogging } from "@/lib/with-logging";
import { setContextUserId, getTraceId } from "@/lib/request-context";
import { logger } from "@/lib/logger";

export const dynamic = "force-dynamic";

const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
} as const;

const NOTHING_RUNNING = () => new Response(null, { status: 204 });

export const GET = withLogging("chat.stream", async (
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) => {
  const { id } = await params;
  const owned = await requireOwnedSession(id);
  if (!owned) {
    return new Response("Session not found", { status: 404 });
  }
  setContextUserId(owned.user.email);

  // The scripted local reply lives inside its own response; there is nothing to join.
  if (!wizardAgentChatEnabled()) return NOTHING_RUNNING();

  try {
    const upstream = await openRunningChatStream(id);
    if (upstream.status === 200 && upstream.body) {
      return new Response(upstream.body, { headers: SSE_HEADERS });
    }
    if (upstream.status !== 204) {
      logger.error(
        { traceId: getTraceId(), sessionId: id, status: upstream.status },
        "chat.stream upstream returned non-ok",
      );
    }
    return NOTHING_RUNNING();
  } catch (err) {
    logger.error({ traceId: getTraceId(), err, sessionId: id }, "chat.stream upstream threw");
    return NOTHING_RUNNING();
  }
});
