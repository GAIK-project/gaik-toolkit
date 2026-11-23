// PoC generation, streamed back as SSE so the workspace can show progress.
//
// With wizard_api configured this scaffolds the real package from the session's
// approved blueprint (#93) and reports the files it wrote; the listing and zip
// endpoints next to this one then serve it. Without wizard_api (mock dev and
// the mock e2e suite) it keeps the original simulated run.

import { NextRequest } from "next/server";
import { getI18n } from "@/lib/i18n";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { apiGeneratePoc, wizardApiEnabled } from "@/lib/wizard-api-client";
import { currentTraceId, safeErrorDetail, withTrace } from "@/lib/safe-error";

export const dynamic = "force-dynamic";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
};

/**
 * Stream the log lines, then one terminal frame. `paced` spaces the lines out
 * for the simulated run; the real scaffolder has already finished by the time
 * we know what it wrote, so there is nothing to pace.
 */
function sse(
  lines: string[],
  { paced, status, scaffolded }: { paced: boolean; status: string; scaffolded?: boolean },
): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const line of lines) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ log: line })}\n\n`));
        if (paced) await sleep(120);
      }
      // `scaffolded: false`: the agent's own package was kept as it was, so
      // nothing saved since is in it.
      const done = scaffolded === undefined ? { done: true, status } : { done: true, status, scaffolded };
      controller.enqueue(encoder.encode(`data: ${JSON.stringify(done)}\n\n`));
      controller.close();
    },
  });
  return new Response(stream, { headers: SSE_HEADERS });
}

export const POST = withLogging(
  "poc.generate",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) {
      return new Response("Session not found", { status: 404 });
    }
    setContextUserId(owned.user.email);
    const session = owned.session;
    const { t } = await getI18n();

    if (!wizardApiEnabled()) {
      // No simulated walk. This route used to stream invented per-step lines
      // and finish with status "success" whether or not anything had been
      // generated, and a green result for work that never happened is the
      // misunderstanding the customer's test report traced back to here. With
      // no backend there is nothing to scaffold with, and that is what it says.
      audit("poc.generate", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "error",
        reason: "wizard_api not configured",
      });
      return sse([t.pocLogNoBackend], { paced: false, status: "failed" });
    }

    try {
      const upstream = await apiGeneratePoc(id);
      if (!upstream.ok) {
        // A rejected call is not "nothing to generate" — say so in the log and
        // in the audit trail rather than reporting a PoC that never happened.
        logger.error(
          { traceId: getTraceId(), sessionId: id, status: upstream.status },
          "poc.generate upstream rejected the request",
        );
        audit("poc.generate", {
          actor: owned.user.email,
          resource: { type: "session", id },
          outcome: "error",
          status: upstream.status,
        });
        // The api says why (the gate, a blueprint it cannot scaffold); the user
        // sees that, not only "generation failed". Only a known code's words
        // pass; any other cause is a generic line with the trace id.
        const detail = safeErrorDetail(
          await upstream.json().catch(() => null),
          currentTraceId(),
          t,
        );
        return sse([t.pocLogFailed, detail.message], { paced: false, status: "failed" });
      }

      const result = (await upstream.json()) as {
        pattern?: string;
        files?: string[];
        regenerated?: boolean;
        scaffolded?: boolean;
        source?: string;
        model?: string;
      };
      const files = result.files ?? [];
      audit("poc.generate", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "success",
        mode: result.source ?? "scaffolder",
        pattern: result.pattern ?? "",
        fileCount: files.length,
        regenerated: Boolean(result.regenerated),
        scaffolded: result.scaffolded !== false,
        model: result.model,
      });
      // The agent's own package is kept, not rewritten — say that rather than
      // reporting files this route did not write.
      const lines =
        result.scaffolded === false
          ? [t.pocLogAgentPackage, t.pocLogDone]
          : [
              t.pocLogGenerating,
              ...files.map((file) => `  ✓ ${t.pocLogWrote} poc/${file}`),
              t.pocLogDone,
            ];
      return sse(lines, { paced: false, status: "success", scaffolded: result.scaffolded !== false });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.generate failed");
      audit("poc.generate", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "error",
      });
      // No answer from the api at all (down, timeout): say so, with the
      // trace id that finds the cause in the log (#228), not the error's text.
      return sse([t.pocLogFailed, withTrace(t.errorUnreachable, currentTraceId())], {
        paced: false,
        status: "failed",
      });
    }
  },
);
