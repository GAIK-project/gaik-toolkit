import type { NextRequest } from "next/server";
import { logger } from "@/lib/logger";
import { TRACE_HEADER, getContext, newTraceId, runWithContext } from "@/lib/request-context";

type AnyHandler = (...args: never[]) => Promise<Response>;

/**
 * Wrap an App Router route handler with structured start/end logging and a
 * per-request traceId (S3-10). Reads `x-trace-id` from the incoming request
 * when the proxy already set one, otherwise generates a fresh one — so this
 * degrades gracefully outside the proxy too (e.g. in unit tests).
 *
 * `event` is the log's operation name (e.g. "blueprint.patch"), independent
 * of the audit event names in lib/audit.ts — this is the operational log,
 * audit() is the separate accountability trail.
 */
export function withLogging<H extends AnyHandler>(event: string, handler: H): H {
  const wrapped = async (...args: Parameters<H>): Promise<Response> => {
    const req = args[0] as NextRequest | undefined;
    const traceId = req?.headers?.get?.(TRACE_HEADER) ?? newTraceId();
    const start = Date.now();

    return runWithContext({ traceId }, async () => {
      const log = logger.child({
        traceId,
        event,
        method: req?.method,
        path: req?.nextUrl?.pathname,
      });
      try {
        const res = await handler(...args);
        const durationMs = Date.now() - start;
        const userId = getContext()?.userId;
        const level = res.status >= 500 ? "error" : res.status >= 400 ? "warn" : "info";
        log[level]({ httpStatus: res.status, durationMs, userId }, "request.end");
        if (!res.headers.has(TRACE_HEADER)) res.headers.set(TRACE_HEADER, traceId);
        return res;
      } catch (err) {
        const durationMs = Date.now() - start;
        const userId = getContext()?.userId;
        log.error({ err, durationMs, userId }, "request.error");
        return new Response("Internal error", {
          status: 500,
          headers: { [TRACE_HEADER]: traceId },
        });
      }
    });
  };
  return wrapped as H;
}
