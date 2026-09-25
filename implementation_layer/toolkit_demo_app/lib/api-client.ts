import toast from "react-hot-toast";
import { getModelSettings } from "./model-settings-store";
import {
  MODEL_SETTINGS_HEADER,
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
    const resetTime = resetHeader ? parseInt(resetHeader, 10) : 0;
    const secondsLeft = Math.max(1, Math.ceil((resetTime - Date.now()) / 1000));

    toast.error(`Too many requests! Please wait ${secondsLeft} seconds.`, {
      duration: 5000,
      icon: "hourglass",
    });

    throw new RateLimitError(resetTime);
  }

  return response;
}
