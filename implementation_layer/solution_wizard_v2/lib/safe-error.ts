/**
 * What of a wizard_api error may reach the browser.
 *
 * wizard_api answers every error as
 * `{ "detail": { "error": "<code>", "message": "...", "trace_id": "...", ... } }`
 * and logs the cause (an exception's text, a server path, a traceback, a
 * Kubernetes message) under that trace id. The relays do not take that on
 * trust: a body passes only when its code is one listed here, and then only
 * its message and the keys a person needs to act (which gate, what is
 * missing, which of the package's files). Anything else (an unknown code, a
 * plain-text or HTML body, an older api that still sends `str(exc)`) becomes
 * a generic message with the request's trace id, which finds the log line.
 */

import { dictionary, getI18n, type Dict } from "@/lib/i18n";
import { TRACE_HEADER, getTraceId, newTraceId } from "@/lib/request-context";

/** Codes whose message is the api's own words for the person, passed on as they are. */
export const KNOWN_ERROR_CODES: ReadonlySet<string> = new Set([
  // gates and readiness
  "gate_not_approved",
  "gate_not_ready",
  "agent_busy",
  "agent_capacity",
  "blueprint_change_required",
  "server_owned_metadata",
  // the package
  "poc_package_incomplete",
  "no_successful_run",
  "blueprint_placeholder",
  "blueprint_not_scaffoldable",
  "package_folder",
  "invalid_blueprint",
  // the sandbox
  "sandbox_busy",
  // input files
  "input_rejected",
  "input_type_not_accepted",
  "input_too_large",
  "input_exists",
  "input_unsafe",
  "scanner_unavailable",
  "input_clash",
  // cases and their process
  "case_state",
  "bpmn_invalid",
  "bpmn_not_runnable",
  "refinement_rejected",
  // a plain refusal: the route's own fixed words ("session not found")
  "not_found",
  "conflict",
  "bad_request",
  "too_large",
  "length_required",
  "invalid_request",
]);

/** Codes kept (the web may branch on them) with the message replaced by our own. */
const INTERNAL_CODES: Record<string, keyof ErrorStrings> = {
  sandbox_unavailable: "errorSandboxUnavailable",
  run_stream_interrupted: "errorGeneric",
  poc_generation_failed: "errorGeneric",
  bpmn_unavailable: "errorGeneric",
  agent_unavailable: "errorGeneric",
  internal_error: "errorGeneric",
  upstream_error: "errorGeneric",
  unavailable: "errorGeneric",
};

/** The extra keys a person needs to act on a refusal; nothing else is passed on. */
const EXTRA_KEYS = ["gate", "gate_step", "status", "missing", "problems", "keys", "feedback"] as const;

export const MESSAGE_MAX_CHARS = 300;
const MAX_LIST_ITEMS = 20;
const TRACE_ID_RE = /^[A-Za-z0-9-]{8,64}$/;

export type ErrorStrings = Pick<Dict, "errorGeneric" | "errorUnreachable" | "errorSandboxUnavailable">;

export type SafeErrorDetail = {
  error: string;
  message: string;
  trace_id: string;
  [key: string]: unknown;
};

/** One line, cut to a readable length. */
export function oneLine(text: string, max = MESSAGE_MAX_CHARS): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/** `template` with the trace id in place of `{trace}`. */
export function withTrace(template: string, traceId: string): string {
  return template.replace("{trace}", traceId);
}

function safeExtra(value: unknown): unknown {
  if (typeof value === "string") return oneLine(value);
  if (typeof value === "number" || typeof value === "boolean" || value === null) return value;
  if (Array.isArray(value)) {
    return value
      .filter((v): v is string => typeof v === "string")
      .slice(0, MAX_LIST_ITEMS)
      .map((v) => oneLine(v));
  }
  return undefined;
}

/**
 * The detail of an upstream error body that may reach the browser. `traceId` is
 * this request's; the api's own is used when it looks like one (they are the
 * same id when the call carried the header, which every call does).
 */
export function safeErrorDetail(body: unknown, traceId: string, strings: ErrorStrings): SafeErrorDetail {
  const raw =
    body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
  const detail = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const upstreamTrace = typeof detail.trace_id === "string" ? detail.trace_id : "";
  const trace = TRACE_ID_RE.test(upstreamTrace) ? upstreamTrace : traceId;
  const code = typeof detail.error === "string" ? detail.error : "";

  if (KNOWN_ERROR_CODES.has(code)) {
    const message = typeof detail.message === "string" ? oneLine(detail.message) : "";
    const safe: SafeErrorDetail = {
      error: code,
      message: message || withTrace(strings.errorGeneric, trace),
      trace_id: trace,
    };
    for (const key of EXTRA_KEYS) {
      if (!(key in detail)) continue;
      const value = safeExtra(detail[key]);
      if (value !== undefined) safe[key] = value;
    }
    return safe;
  }
  const internal = INTERNAL_CODES[code];
  return {
    error: internal ? code : "internal_error",
    message: withTrace(strings[internal ?? "errorGeneric"], trace),
    trace_id: trace,
  };
}

/** The current request's trace id (a fresh one outside withLogging). */
export function currentTraceId(): string {
  return getTraceId() ?? newTraceId();
}

/** The error strings in the caller's locale, or the default locale's outside a request. */
export async function errorStrings(): Promise<ErrorStrings> {
  try {
    return (await getI18n()).t;
  } catch {
    return dictionary();
  }
}

/** A browser answer `{ detail }` for an error the relay itself decided on. */
export function errorResponse(
  detail: SafeErrorDetail,
  status: number,
  extraHeaders: Record<string, string> = {},
): Response {
  return Response.json(
    { detail },
    {
      status,
      headers: { ...extraHeaders, [TRACE_HEADER]: detail.trace_id, "Cache-Control": "no-store" },
    },
  );
}

/**
 * Relay a failed upstream answer: its status (or `status`), and a detail that
 * passed `safeErrorDetail`. The body is read here; nothing else of it is sent.
 */
export async function relayError(upstream: Response, status = upstream.status): Promise<Response> {
  const body = await upstream.json().catch(() => null);
  // When to try again (a busy sandbox) is for the client; no other header is.
  const retryAfter = upstream.headers.get("retry-after");
  return errorResponse(
    safeErrorDetail(body, currentTraceId(), await errorStrings()),
    status,
    retryAfter && /^\d{1,4}$/.test(retryAfter) ? { "Retry-After": retryAfter } : {},
  );
}

/** The answer for an upstream that did not answer at all (down, timeout). */
export async function unreachableResponse(status = 502): Promise<Response> {
  const trace = currentTraceId();
  const strings = await errorStrings();
  return errorResponse(
    { error: "upstream_unreachable", message: withTrace(strings.errorUnreachable, trace), trace_id: trace },
    status,
  );
}

/**
 * Pass an SSE stream through, rewriting only its error frames
 * (`{"error": true, ...}`) to a code and a message that passed
 * `safeErrorDetail`. Every other frame (log lines, heartbeats, the done frame)
 * is passed on as it came.
 */
export function sanitizeSseErrors(
  body: ReadableStream<Uint8Array>,
  traceId: string,
  strings: ErrorStrings,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";

  const rewrite = (frame: string): string => {
    if (!frame.startsWith("data: ")) return frame;
    let evt: unknown;
    try {
      evt = JSON.parse(frame.slice(6));
    } catch {
      return frame;
    }
    if (!evt || typeof evt !== "object" || !(evt as { error?: unknown }).error) return frame;
    const e = evt as { code?: unknown; message?: unknown; trace_id?: unknown };
    const safe = safeErrorDetail(
      { detail: { error: e.code, message: e.message, trace_id: e.trace_id } },
      traceId,
      strings,
    );
    return `data: ${JSON.stringify({ error: true, code: safe.error, message: safe.message, trace_id: safe.trace_id })}`;
  };

  return body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        buffer += decoder.decode(chunk, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) controller.enqueue(encoder.encode(`${rewrite(frame)}\n\n`));
      },
      flush(controller) {
        buffer += decoder.decode();
        if (buffer) controller.enqueue(encoder.encode(rewrite(buffer)));
      },
    }),
  );
}
