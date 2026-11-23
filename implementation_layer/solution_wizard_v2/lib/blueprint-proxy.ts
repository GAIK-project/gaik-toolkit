/**
 * What the blueprint edit routes share (operations, undo, the full draft, the
 * diagram's layout and mapping): they relay to wizard_api, which alone holds
 * the full draft. Each route checks the owner itself (requireOwnedSession);
 * wizard_api checks the user again from the X-Wizard-User-Id that
 * outgoingHeaders() adds. A refusal is passed on only through lib/safe-error,
 * and a success without the session's internals (its folder, messages,
 * metadata), which the browser has no use for.
 */

import type { NextRequest } from "next/server";
import { logger } from "@/lib/logger";
import { getTraceId } from "@/lib/request-context";
import { currentTraceId, errorResponse, relayError, unreachableResponse } from "@/lib/safe-error";
import { declaredLengthProblem } from "@/lib/upload-limits";

export const NO_STORE = { "Cache-Control": "no-store" };

/** Without wizard_api (local mock mode) there is no full draft to edit. */
export function needsWizardApi(): Response {
  return Response.json({ error: "needs_wizard_api" }, { status: 503, headers: NO_STORE });
}

function refusal(status: number, error: string, message: string): Response {
  return errorResponse({ error, message, trace_id: currentTraceId() }, status);
}

/**
 * The request's JSON body, at most `maxBytes`, or the refusal to answer with.
 * The length is checked before the body is read (a body that does not say its
 * length would be buffered whole first) and again once it is read.
 */
export async function readLimitedJson(
  req: NextRequest,
  maxBytes: number,
): Promise<{ body: unknown } | { refused: Response }> {
  const declared = declaredLengthProblem(req.headers.get("content-length"), maxBytes, 0);
  if (declared?.status === 411) {
    return { refused: refusal(411, "length_required", "send the request with a content-length") };
  }
  const tooLarge = () =>
    refusal(413, "too_large", `the request is larger than ${Math.floor(maxBytes / 1024)} KB`);
  if (declared) return { refused: tooLarge() };
  const text = await req.text();
  if (Buffer.byteLength(text, "utf8") > maxBytes) return { refused: tooLarge() };
  try {
    return { body: JSON.parse(text) as unknown };
  } catch {
    return { refused: refusal(400, "bad_request", "the request is not JSON") };
  }
}

/** The session as the browser gets it after an edit: what the workspace shows and the version. */
export function publicSession(session: unknown): Record<string, unknown> | null {
  if (!session || typeof session !== "object") return null;
  const s = session as Record<string, unknown>;
  return {
    id: s.id,
    step: s.step,
    gate_statuses: s.gate_statuses,
    active_version: s.active_version,
    blueprint: s.blueprint,
  };
}

/**
 * Calls wizard_api and answers with `onOk(body)` for a 2xx (its JSON body;
 * null for a 204), the refusal through lib/safe-error otherwise, and 502 when
 * it does not answer or answers a 2xx that is not JSON (nothing of that body
 * is passed on). `onDone` hears whether the call succeeded, was refused (4xx)
 * or failed.
 */
export async function relayUpstream(
  call: () => Promise<Response>,
  onOk: (body: unknown) => Response,
  { event, sessionId, onDone }: {
    event: string;
    sessionId: string;
    onDone?: (outcome: "success" | "denied" | "error") => void;
  },
): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await call();
  } catch (err) {
    logger.error({ traceId: getTraceId(), err, sessionId }, `${event} failed`);
    onDone?.("error");
    return unreachableResponse();
  }
  if (!upstream.ok) {
    onDone?.(upstream.status < 500 ? "denied" : "error");
    return relayError(upstream);
  }
  let body: unknown = null;
  if (upstream.status !== 204) {
    try {
      body = JSON.parse(await upstream.text());
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId, status: upstream.status }, `${event} answer is not JSON`);
      onDone?.("error");
      return unreachableResponse();
    }
  }
  onDone?.("success");
  return onOk(body);
}

/** A 2xx edit answer `{session, warnings, needs_attention, bpmn_changed}` with the session trimmed. */
export function editResult(body: unknown): Response {
  const data = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  return Response.json(
    {
      session: publicSession(data.session),
      warnings: data.warnings ?? [],
      needs_attention: data.needs_attention ?? [],
      bpmn_changed: Boolean(data.bpmn_changed),
    },
    { headers: NO_STORE },
  );
}

/** A 2xx JSON answer passed on as it came, uncached. */
export function passJson(body: unknown): Response {
  return Response.json(body, { headers: NO_STORE });
}
