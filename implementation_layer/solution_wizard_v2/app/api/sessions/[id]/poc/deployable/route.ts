// The deployable package (#143): the PoC as someone else receives it, served by
// wizard_api only after a sandbox run it recorded as successful. Relays the zip;
// relays the api's 409 (no successful run yet, package incomplete) as JSON so
// the tab can say why the download is not open. 404 in mock mode.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { aiHeaders, aiModel } from "@/lib/ai-marking";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { relayError } from "@/lib/safe-error";
import { wizardApiEnabled, apiGetDeployablePocZip } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const GET = withLogging(
  "poc.deployable",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
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
      const upstream = await apiGetDeployablePocZip(id);
      if (upstream.status === 409) {
        // "run the PoC successfully first" / "package incomplete": the api's
        // own words, passed on for the tab to show.
        return relayError(upstream, 409);
      }
      if (upstream.status === 404) {
        return new Response("no PoC generated yet", { status: 404 });
      }
      if (!upstream.ok || !upstream.body) {
        logger.error(
          { traceId: getTraceId(), sessionId: id, status: upstream.status },
          "poc.deployable upstream rejected the request",
        );
        return new Response("deployable package failed", { status: 502 });
      }
      audit("poc.deployable", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "success",
        action: upstream.headers.get("X-Wizard-Run-Id") ?? undefined,
        model: aiModel(upstream),
      });
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename="poc-${id}-deployable.zip"`,
          "Cache-Control": "no-store",
          ...aiHeaders(upstream),
        },
      });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.deployable failed");
      return new Response("deployable package failed", { status: 500 });
    }
  },
);
