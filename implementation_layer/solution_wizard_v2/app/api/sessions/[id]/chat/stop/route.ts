// Stops the reply that is being written for a session.
//
// A reply can take minutes. The page could only stop following it, which left
// the wizard working and the next message refused. This passes the stop on to
// wizard_api, which interrupts the agent: the reply's own stream then says that
// it was stopped and closes once the exchange is stored.
//
// 202: the stop is on its way. 409: no reply is being written (it ended a
// moment ago, or the message has not reached the wizard yet), so there is
// nothing to stop now.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { stopMockReply } from "@/lib/mock-sessions";
import { stopAgentChat, wizardAgentChatEnabled } from "@/lib/wizard-api-client";
import { withLogging } from "@/lib/with-logging";
import { setContextUserId, getTraceId } from "@/lib/request-context";
import { logger } from "@/lib/logger";

export const dynamic = "force-dynamic";

const STOPPING = () => Response.json({ stopping: true }, { status: 202 });
const NOTHING_RUNNING = () => Response.json({ error: "no_reply_running" }, { status: 409 });

export const POST = withLogging("chat.stop", async (
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) => {
  const { id } = await params;
  const owned = await requireOwnedSession(id);
  if (!owned) {
    return new Response("Session not found", { status: 404 });
  }
  setContextUserId(owned.user.email);

  // Local dev without wizard_api: the scripted reply is stopped where it streams.
  if (!wizardAgentChatEnabled()) {
    return stopMockReply(id) ? STOPPING() : NOTHING_RUNNING();
  }

  try {
    const upstream = await stopAgentChat(id);
    if (upstream.status === 202) return STOPPING();
    if (upstream.status === 409) return NOTHING_RUNNING();
    logger.error(
      { traceId: getTraceId(), sessionId: id, status: upstream.status },
      "chat.stop upstream returned non-ok",
    );
    return Response.json({ error: "upstream", status: upstream.status }, { status: 502 });
  } catch (err) {
    logger.error({ traceId: getTraceId(), err, sessionId: id }, "chat.stop upstream threw");
    return Response.json({ error: "upstream" }, { status: 502 });
  }
});
