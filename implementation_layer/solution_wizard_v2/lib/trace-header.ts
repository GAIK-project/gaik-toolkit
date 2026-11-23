/**
 * Just the header name, split out from lib/request-context.ts so that
 * proxy.ts can reference it without pulling in node:crypto /
 * node:async_hooks with it.
 */
export const TRACE_HEADER = "x-trace-id";
