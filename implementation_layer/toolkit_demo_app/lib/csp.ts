import type { NextRequest, NextResponse } from "next/server";
import { isApiPath } from "./backend-target";
import { routedPath } from "./request-path";

/**
 * The Content-Security-Policy of a page, built per request around a nonce.
 *
 * proxy.ts makes a nonce for every page request and sends the policy twice: on
 * the request, where Next reads it to stamp the nonce on its own inline
 * bootstrap and chunk scripts, and on the response, which the browser enforces.
 * The root layout waits for the request (app/layout.tsx), so no page is
 * prerendered with a stale nonce or none.
 *
 * Every response, a page's included, also carries the static base policy from
 * next.config.ts (lib/security-headers.ts). The page policy repeats each of its
 * directives unchanged, so a browser that gets both enforces the page policy.
 *
 * `'strict-dynamic'`: a script the nonced bootstrap loads (Next's chunks,
 * `next/script`, PostHog's own bundles) is trusted through it. Styles keep
 * `'unsafe-inline'`: React renders `style` attributes and the UI libraries set
 * them at run time, and a nonce in `style-src` would switch that off.
 */

export const CSP_HEADER = "Content-Security-Policy";

/** The policy every response carries; sent from next.config.ts. */
export const BASE_CSP_DIRECTIVES = [
  // The PDF previews frame this site's own pages.
  "frame-ancestors 'self'",
  "base-uri 'self'",
  "object-src 'none'",
];

/**
 * CSC Allas: the video search and subtitle demos play videos and show
 * thumbnails from presigned Allas URLs (api/utils/s3.py, path-style). Keep in
 * step with the API's ALLAS_ENDPOINT_URL.
 */
export const ALLAS_ORIGIN = "https://a3s.fi";

/** 128 bits of randomness, base64: the CSP spec's minimum for a nonce. */
export function makeNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/** The origin of a configured URL, or nothing when it is unset or not http(s). */
function originOf(url: string | undefined): string[] {
  if (!url) return [];
  try {
    const { protocol, origin } = new URL(url);
    return protocol === "https:" || protocol === "http:" ? [origin] : [];
  } catch {
    return [];
  }
}

export function buildCsp({
  nonce,
  nodeEnv = process.env.NODE_ENV,
  supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL,
  posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST,
  chatUrl = process.env.NEXT_PUBLIC_CHAT_URL,
}: {
  nonce: string;
  nodeEnv?: string;
  supabaseUrl?: string;
  posthogHost?: string;
  chatUrl?: string;
}): string {
  const chat = originOf(chatUrl);
  const join = (...parts: string[]) => parts.join(" ");
  return [
    "default-src 'self'",
    join(
      "script-src 'self'",
      `'nonce-${nonce}'`,
      "'strict-dynamic'",
      // React and Next's dev server need eval in development only.
      ...(nodeEnv === "development" ? ["'unsafe-eval'"] : []),
    ),
    join("style-src 'self' 'unsafe-inline'", ...chat),
    // https: for the link previews' images, whose hosts vary; blob: for
    // uploaded images shown before they are sent.
    "img-src 'self' data: blob: https:",
    join("font-src 'self' data:", ...chat),
    `media-src 'self' blob: ${ALLAS_ORIGIN}`,
    // Uploaded PDFs are previewed from blob: URLs; the examples from this site.
    join("frame-src 'self' blob:", ...chat),
    // This site's own API and PostHog proxy (/a), Supabase for the session,
    // PostHog's host for the provider's own init, and the chat widget.
    join(
      "connect-src 'self'",
      ...originOf(supabaseUrl),
      ...originOf(posthogHost),
      ...chat,
    ),
    "worker-src 'self' blob:",
    "form-action 'self'",
    ...BASE_CSP_DIRECTIVES,
  ].join("; ");
}

/**
 * Whether a path is a page that gets the nonce policy. API responses (the
 * backend's own pages, such as its API docs, included) and the PostHog rewrite
 * under /a keep the base policy, and their requests carry no policy onwards.
 */
export function isPagePath(pathname: string): boolean {
  const path = routedPath(pathname) ?? pathname;
  return !isApiPath(path) && path !== "/a" && !path.startsWith("/a/");
}

/**
 * Makes the nonce and puts the policy on the request, so whatever the proxy
 * returns, `NextResponse.next({ request })` included, hands it to the
 * renderer. Returns the policy for `setCsp`.
 */
export function attachCsp(request: NextRequest, nodeEnv?: string): string {
  const csp = buildCsp({ nonce: makeNonce(), nodeEnv });
  request.headers.set(CSP_HEADER, csp);
  return csp;
}

export function setCsp<T extends NextResponse>(response: T, csp: string): T {
  response.headers.set(CSP_HEADER, csp);
  return response;
}
