// A copy of what the wizard holds for the session, for its owner. wizard_api
// builds the zip; this relays it. 404 in mock mode, where nothing is stored.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { apiExportSession, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "session.export",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) return new Response("Export not available", { status: 404 });
    try {
      const upstream = await apiExportSession(id);
      if (!upstream.ok || !upstream.body) {
        logger.error(
          { traceId: getTraceId(), sessionId: id, status: upstream.status },
          "session.export upstream rejected the request",
        );
        return new Response("Export failed", { status: 502 });
      }
      audit("session.export", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "success",
      });
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename="session-${id}.zip"`,
          "Cache-Control": "no-store",
        },
      });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "session.export failed");
      return new Response("Export failed", { status: 500 });
    }
  },
);
