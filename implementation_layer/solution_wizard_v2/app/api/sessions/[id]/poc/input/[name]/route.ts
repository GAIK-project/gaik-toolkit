// Remove one sample input file (#95). wizard_api validates the name (it may not
// leave sample_input/); this route relays 204, or 404 for a file or package
// that is not there.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { wizardApiEnabled, apiDeletePocInput } from "@/lib/wizard-api-client";
import { relayError } from "@/lib/safe-error";

export const dynamic = "force-dynamic";

export const DELETE = withLogging(
  "poc.input.delete",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string; name: string }> }) => {
    const { id, name } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) {
      return new Response("Session not found", { status: 404 });
    }
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) {
      return new Response("PoC input is not available", { status: 404 });
    }
    try {
      const upstream = await apiDeletePocInput(id, name);
      if (upstream.status === 204) {
        audit("poc.input.delete", {
          actor: owned.user.email,
          resource: { type: "session", id },
          outcome: "success",
          action: name,
        });
        return new Response(null, { status: 204 });
      }
      return relayError(upstream, upstream.status === 404 ? 404 : 502);
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.input.delete failed");
      return new Response("delete failed", { status: 500 });
    }
  },
);
