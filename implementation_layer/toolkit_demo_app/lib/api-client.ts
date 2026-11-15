import toast from "react-hot-toast";
import { getModelSettings } from "./model-settings-store";
import { getServerModel } from "./server-model-store";
import {
  MODEL_SETTINGS_HEADER,
  SERVER_MODEL_HEADER,
  encodeModelSettings,
  supportsModelSettings,
} from "./model-settings";

export class RateLimitError extends Error {
  readonly resetTime: number;

  constructor(resetTime: number) {
    super("Rate limit exceeded");
    this.name = "RateLimitError";
    this.resetTime = resetTime;
  }
}

/**
 * Fetch wrapper that handles rate limit errors with toast notifications
 */
export async function apiFetch(
  url: string,
  options?: RequestInit,
): Promise<Response> {
  const headers = new Headers(options?.headers);
  // Only attach a credential to a supported same-origin POST, never to external
  // example downloads, GETs, analytics or unrelated API routes.
  const target =
    typeof window !== "undefined" ? new URL(url, window.location.origin) : null;
  const supported =
    typeof window !== "undefined" &&
    target?.origin === window.location.origin &&
    supportsModelSettings(target.pathname, options?.method ?? "GET");
  const settings = getModelSettings();
  if (supported && settings && !headers.has(MODEL_SETTINGS_HEADER)) {
    headers.set(MODEL_SETTINGS_HEADER, encodeModelSettings(settings));
  } else if (!supported) {
    headers.delete(MODEL_SETTINGS_HEADER);
  }
  // No own key: run on the server model the user picked, if any.
  const serverModel = getServerModel();
  if (
    supported &&
    !headers.has(MODEL_SETTINGS_HEADER) &&
    serverModel &&
    !headers.has(SERVER_MODEL_HEADER)
  ) {
    headers.set(SERVER_MODEL_HEADER, serverModel);
  } else if (!supported) {
    headers.delete(SERVER_MODEL_HEADER);
  }
  const response = await fetch(url, {
    ...options,
    headers,
    // A redirect must never forward a browser-supplied credential to another URL.
    ...(headers.has(MODEL_SETTINGS_HEADER)
      ? { redirect: "error" as const }
      : {}),
  });

  if (response.status === 429) {
    const resetHeader = response.headers.get("X-RateLimit-Reset");
    if (!resetHeader) {
      // The daily trial allowance (lib/trial.ts) has no countdown; say its own text.
      const body = (await response
        .clone()
        .json()
        .catch(() => null)) as { error?: unknown } | null;
      toast.error(
        typeof body?.error === "string" ? body.error : "Too many requests.",
        { duration: 8000 },
      );
      throw new RateLimitError(0);
    }
    const resetTime = resetHeader ? parseInt(resetHeader, 10) : 0;
    const secondsLeft = Math.max(1, Math.ceil((resetTime - Date.now()) / 1000));

    toast.error(`Too many requests! Please wait ${secondsLeft} seconds.`, {
      duration: 5000,
      icon: "hourglass",
    });

    throw new RateLimitError(resetTime);
  }

  // The proxy's own refusals (sign in, pending approval, a used-up trial) say why
  // in `error`, while the demo pages read the backend's `detail`; give them both
  // so the page shows the reason instead of its generic fallback.
  if (!response.ok) {
    const body = (await response
      .clone()
      .json()
      .catch(() => null)) as Record<string, unknown> | null;
    if (body && typeof body.error === "string" && body.detail === undefined)
      return Response.json(
        { ...body, detail: body.error },
        { status: response.status, statusText: response.statusText },
      );
  }

  return response;
}

/**
 * Why a failed request failed, for the page to show: the backend's `detail` or the
 * proxy's `error` (sign in, pending approval, a used-up trial), else `fallback`.
 */
export async function failureMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  const body = (await response.json().catch(() => null)) as Record<
    string,
    unknown
  > | null;
  if (typeof body?.detail === "string") return body.detail;
  if (typeof body?.error === "string") return body.error;
  return fallback;
}
