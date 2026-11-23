import { NextRequest } from "next/server";
import { BPMN_VISUAL_STEP, hasBpmnSpike } from "@/lib/bpmn-spike";
import { fetchBpmnXmlForSession } from "@/lib/bpmn-generate";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "bpmn.get",
  async (
    _req: NextRequest,
    { params }: { params: Promise<{ id: string }> },
  ) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) {
      return new Response("Session not found", { status: 404 });
    }
    setContextUserId(owned.user.email);
    if (!hasBpmnSpike(id) || owned.session.step < BPMN_VISUAL_STEP) {
      return new Response("BPMN not available for this session", { status: 404 });
    }

    try {
      const xml = await fetchBpmnXmlForSession(id, owned.session.blueprint);
      return new Response(xml, {
        headers: {
          "Content-Type": "application/xml; charset=utf-8",
          "Cache-Control": "no-store",
          // The diagram is AI output; its first line says so, this header too.
          "X-AI-Generated": "true",
        },
      });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "bpmn.get failed");
      return new Response("BPMN generation failed", { status: 500 });
    }
  },
);
