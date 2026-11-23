// One file a finished sandbox run wrote to output/, as it wrote it — the PDF a
// report PoC produces included. wizard_api decodes it from the run's log; the
// run's own output folder goes with its pod and was out of the user's reach.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { aiHeaders } from "@/lib/ai-marking";
import { apiGetPocRunFile, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "poc.run.file",
  async (
    _req: NextRequest,
    { params }: { params: Promise<{ id: string; runId: string; name: string }> },
  ) => {
    const { id, runId, name } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) return new Response("File not found", { status: 404 });
    try {
      const upstream = await apiGetPocRunFile(id, runId, name);
      if (!upstream.ok) {
        return new Response("File not found", { status: upstream.status === 503 ? 503 : 404 });
      }
      return new Response(upstream.body, {
        status: 200,
        headers: {
          "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
          "Content-Disposition": upstream.headers.get("content-disposition") ?? "attachment",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          ...aiHeaders(upstream),
        },
      });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id, runId }, "poc.run.file failed");
      return new Response("File not found", { status: 502 });
    }
  },
);
