import { NextRequest } from "next/server";
import { BPMN_VISUAL_STEP, hasBpmnSpike } from "@/lib/bpmn-spike";
import { fetchBpmnXmlForSession } from "@/lib/bpmn-generate";
import { parseDataObjectsParam } from "@/lib/bpmn-show-data";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "bpmn.get",
  async (
    req: NextRequest,
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

    // ?data_objects=0 draws the diagram without data objects ("Show data" off).
    const dataObjects = parseDataObjectsParam(req.nextUrl.searchParams.get("data_objects"));
    if (dataObjects === null) {
      return new Response("data_objects must be 0 or 1", { status: 400 });
    }

    try {
      const xml = await fetchBpmnXmlForSession(id, owned.session.blueprint, { dataObjects });
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
