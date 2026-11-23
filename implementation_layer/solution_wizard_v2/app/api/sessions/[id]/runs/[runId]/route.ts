// Where a sandbox run got to, for a PoC tab that was not following it: after a
// reload the tab asks for the session's latest run and shows its result again.
// wizard_api answers from the Job, or from the copy saved when the run ended
// once the Job has been reaped. Mock mode has no runs.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { apiGetPocRun, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "poc.run.status",
  async (
    _req: NextRequest,
    { params }: { params: Promise<{ id: string; runId: string }> },
  ) => {
    const { id, runId } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) return new Response("Run not found", { status: 404 });
    try {
      const upstream = await apiGetPocRun(id, runId);
      if (!upstream.ok) return new Response("Run not found", { status: upstream.status === 404 ? 404 : 502 });
      return Response.json(await upstream.json());
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id, runId }, "poc.run.status failed");
      return new Response("Run status unavailable", { status: 502 });
    }
  },
);
