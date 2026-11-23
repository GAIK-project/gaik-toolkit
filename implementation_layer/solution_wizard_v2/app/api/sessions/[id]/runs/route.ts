// Start a sandbox run of the session's PoC package (#94 -> #91).
//
// A thin proxy: wizard_api owns the gate check, the package completeness check
// and the Job. Deliberately no mock path — a run that did not happen must not
// be able to report that it did, which is the misunderstanding the previous
// simulated "Run PoC" created with the customer.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { relayHeaders } from "@/lib/sandbox-busy";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { currentTraceId, errorResponse, errorStrings, relayError, unreachableResponse, withTrace } from "@/lib/safe-error";
import { apiCreatePocRun, wizardAgentChatEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const POST = withLogging(
  "poc.run.create",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    if (!wizardAgentChatEnabled()) {
      const trace = currentTraceId();
      const strings = await errorStrings();
      return errorResponse(
        {
          error: "sandbox_unavailable",
          message: withTrace(strings.errorSandboxUnavailable, trace),
          trace_id: trace,
        },
        503,
      );
    }

    let upstream: Response;
    try {
      upstream = await apiCreatePocRun(id);
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "apiCreatePocRun failed");
      return unreachableResponse();
    }
    // Pass the upstream status through: 409 (gate, incomplete package), 429
    // (sandbox busy) and 503 (sandbox unavailable) say something the user needs
    // to read. Only a known code's words pass; anything else is generic.
    if (!upstream.ok) return relayError(upstream);
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: relayHeaders(upstream, { "Content-Type": "application/json" }),
    });
  },
);
