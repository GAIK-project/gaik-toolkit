/**
 * The api's answer when the sandbox has no room for another run yet: 429 with
 * `{"detail": {"error": "sandbox_busy"}}` and a Retry-After header. The api's own
 * message names stack-wide limits, so the browser shows its localized text
 * instead, and the relays pass Retry-After on so the page knows when to ask again.
 */

export const SANDBOX_BUSY = "sandbox_busy";

/** Retry-After when the api sends none, or one that cannot be read. */
export const DEFAULT_RETRY_AFTER_S = 30;
/** A page waits at most this long before it asks again by itself. */
export const MAX_RETRY_AFTER_S = 300;

/** Whether an api answer says the sandbox is busy. */
export function isSandboxBusy(status: number, body: unknown): boolean {
  const detail = (body as { detail?: unknown } | null)?.detail;
  const error =
    detail && typeof detail === "object" ? (detail as { error?: unknown }).error : undefined;
  return error === SANDBOX_BUSY || (status === 429 && error === undefined);
}

/**
 * Milliseconds to wait before asking again, from a Retry-After value (seconds or
 * an HTTP date). Bounded to 1 s .. MAX_RETRY_AFTER_S.
 */
export function retryAfterMs(value: string | null | undefined, now: number = Date.now()): number {
  let seconds = DEFAULT_RETRY_AFTER_S;
  const text = (value ?? "").trim();
  if (/^\d+$/.test(text)) {
    seconds = Number(text);
  } else if (text) {
    const at = Date.parse(text);
    if (!Number.isNaN(at)) seconds = Math.ceil((at - now) / 1000);
  }
  return Math.min(Math.max(seconds, 1), MAX_RETRY_AFTER_S) * 1000;
}

/** The relay's response headers, with the api's Retry-After passed on when it sent one. */
export function relayHeaders(upstream: Response, headers: Record<string, string>): Record<string, string> {
  const retryAfter = upstream.headers.get("retry-after");
  return retryAfter ? { ...headers, "Retry-After": retryAfter } : headers;
}

/**
 * When the PoC tab should ask for the preflight of a version again after the
 * api refused to start one: after Retry-After for a busy sandbox, never for
 * anything else (an incomplete package or a deployment without a sandbox does
 * not change by waiting).
 */
export function preflightRetryDelayMs(status: number, retryAfter: string | null): number | null {
  return status === 429 ? retryAfterMs(retryAfter) : null;
}
