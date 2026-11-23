// Streams the generated PoC folder (zip) to the browser. Proxies the wizard_api
// zip response straight through. 404 in mock mode or before the PoC exists;
// the api's 409 (package incomplete) is relayed as JSON with its reasons.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { aiHeaders, aiModel } from "@/lib/ai-marking";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { relayError } from "@/lib/safe-error";
import { wizardApiEnabled, apiGetPocZip } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "poc.download",
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

    if (!wizardApiEnabled()) {
      return new Response("PoC not available", { status: 404 });
    }
    try {
      const upstream = await apiGetPocZip(id);
      if (upstream.status === 409) {
        // "the generated package is not complete": the api's own reasons, not
        // a failed call.
        return relayError(upstream, 409);
      }
      if (!upstream.ok || !upstream.body) {
        // Don't report an auth or server failure as "nothing generated" — that
        // sends the reader looking for a missing PoC instead of a broken call.
        if (upstream.status !== 404) {
          logger.error(
            { traceId: getTraceId(), sessionId: id, status: upstream.status },
            "poc.download upstream rejected the request",
          );
          return new Response("PoC download failed", { status: 502 });
        }
        return new Response("no PoC generated yet", { status: 404 });
      }
      audit("poc.download", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "success",
        model: aiModel(upstream),
      });
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename="poc-${id}.zip"`,
          "Cache-Control": "no-store",
          ...aiHeaders(upstream),
        },
      });
    } catch (err) {
      logger.error(
        { traceId: getTraceId(), err, sessionId: id },
        "poc.download failed",
      );
      return new Response("PoC download failed", { status: 500 });
    }
  },
);
