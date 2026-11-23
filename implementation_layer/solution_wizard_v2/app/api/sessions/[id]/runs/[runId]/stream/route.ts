// Follow one sandbox run's output (#94 -> #92).
//
// The SSE frames are wizard_api's and are piped through, so the UI reads the
// same contract the chat stream uses:
//   data: {"log": "..."} · {"heartbeat": true} · {"done": true, "phase": "..."}
// An error frame ({"error": true, ...}) passes only as a known code and its
// words (lib/safe-error); every other frame is passed on as it came.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { currentTraceId, errorStrings, relayError, sanitizeSseErrors, unreachableResponse } from "@/lib/safe-error";
import { apiStreamPocRun } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
};

export const GET = withLogging(
  "poc.run.stream",
  async (
    _req: NextRequest,
    { params }: { params: Promise<{ id: string; runId: string }> },
  ) => {
    const { id, runId } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    let upstream: Response;
    try {
      upstream = await apiStreamPocRun(id, runId);
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id, runId }, "poc.run.stream failed");
      return unreachableResponse();
    }
    if (!upstream.ok || !upstream.body) {
      return relayError(upstream, upstream.ok ? 502 : upstream.status);
    }
    const body = sanitizeSseErrors(upstream.body, currentTraceId(), await errorStrings());
    return new Response(body, { headers: SSE_HEADERS });
  },
);
