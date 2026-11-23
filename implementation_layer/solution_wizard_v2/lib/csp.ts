import type { NextRequest, NextResponse } from "next/server";

/**
 * The Content-Security-Policy, built per request around a nonce.
 *
 * Next.js emits its bootstrap as inline scripts, so a static policy had to
 * allow `'unsafe-inline'` for scripts (lib/security-headers.ts, until #133's
 * follow-up). Now the middleware makes a nonce for every request and sends the
 * policy in two places: as a request header, which Next reads to stamp the
 * nonce on its own inline scripts and chunk tags (app-render reads the nonce
 * from the request's `content-security-policy`), and as the response header
 * the browser enforces. Every page renders per request (the root layout reads
 * the locale cookie), so no prerendered HTML carries a stale nonce.
 *
 * `'strict-dynamic'`: a script the nonced bootstrap loads (Next's chunks,
 * `import()` of the bpmn-js and React Flow bundles) is trusted through it; a
 * browser without it falls back to `'self'`. Styles keep `'unsafe-inline'`:
 * bpmn-js and React Flow set element styles directly on the canvas.
 */

/** Request header the middleware sets so a server component can read the nonce. */
export const NONCE_HEADER = "x-nonce";
export const CSP_HEADER = "Content-Security-Policy";

/** 128 bits of randomness, base64: the CSP spec's minimum for a nonce. */
export function makeNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/**
 * `'unsafe-eval'` is a development-only allowance: Next's dev server (React
 * Refresh, source-map eval) needs it, the production bundle does not, and
 * bpmn-js does not eval either. Allowing it in production would turn any
 * injected string into executable code for nothing (review T6).
 */
export function buildCsp({
  nonce,
  nodeEnv = process.env.NODE_ENV,
}: {
  nonce: string;
  nodeEnv?: string;
}): string {
  const scriptSrc = [
    "script-src 'self'",
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    ...(nodeEnv === "development" ? ["'unsafe-eval'"] : []),
  ].join(" ");
  return [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    // data:/blob: — bpmn-js exports diagrams as blob URLs, next/font inlines.
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    // Same-origin only: the browser never talks to wizard_api directly, all
    // API traffic goes through this app's own server-side proxy.
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

/**
 * The policy for the routes the middleware matcher leaves out (the file
 * uploads, middleware.ts). They answer JSON and render nothing, so nothing may
 * load at all. Set from next.config.ts, which the middleware never reaches.
 */
export const JSON_ROUTE_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'";

/**
 * Makes the nonce and puts the policy on the request, so that whatever the
 * middleware returns — `NextResponse.next({ request })` included — hands it to
 * the renderer. Returns the policy for `setCsp` on the response.
 */
export function attachCsp(request: NextRequest, nodeEnv?: string): string {
  const nonce = makeNonce();
  const csp = buildCsp({ nonce, nodeEnv });
  request.headers.set(NONCE_HEADER, nonce);
  request.headers.set(CSP_HEADER, csp);
  return csp;
}

export function setCsp<T extends NextResponse>(response: T, csp: string): T {
  response.headers.set(CSP_HEADER, csp);
  return response;
}
