// Start the preflight of the session's PoC package (#252 -> wizard_api).
//
// A thin proxy, like the run route: wizard_api owns the package check and the
// Job. The preflight calls no model and needs no input; its log is followed on
// the same run stream as a real run. No mock path: a check that did not happen
// must not be able to report that it passed.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { relayHeaders } from "@/lib/sandbox-busy";
import { withLogging } from "@/lib/with-logging";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { currentTraceId, errorResponse, errorStrings, relayError, unreachableResponse, withTrace } from "@/lib/safe-error";
import { apiCreatePocCheck, wizardAgentChatEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const POST = withLogging(
  "poc.check.create",
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
      upstream = await apiCreatePocCheck(id);
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "apiCreatePocCheck failed");
      return unreachableResponse();
    }
    // A refusal passes only as a known code and its words (relayError).
    if (!upstream.ok) return relayError(upstream);
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: relayHeaders(upstream, { "Content-Type": "application/json" }),
    });
  },
);
