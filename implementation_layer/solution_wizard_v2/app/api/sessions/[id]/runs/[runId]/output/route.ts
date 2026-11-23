// What a finished sandbox run wrote to output/, read by wizard_api from the
// run's log between the output markers. The PoC tab shows it as the result
// instead of leaving the person to find it in the raw log. Mock mode and an
// upstream failure answer with no files, so the log is all the tab shows then.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { apiGetPocRunOutput, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

const NOTHING = { record: null, validation: null, transcript: "", document: "", files: [] };

export const GET = withLogging(
  "poc.run.output",
  async (
    _req: NextRequest,
    { params }: { params: Promise<{ id: string; runId: string }> },
  ) => {
    const { id, runId } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) return Response.json({ run_id: runId, ...NOTHING });
    try {
      const upstream = await apiGetPocRunOutput(id, runId);
      if (upstream.status === 404) return new Response("Run not found", { status: 404 });
      if (!upstream.ok) return Response.json({ run_id: runId, ...NOTHING });
      return Response.json(await upstream.json());
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id, runId }, "poc.run.output failed");
      return Response.json({ run_id: runId, ...NOTHING });
    }
  },
);
