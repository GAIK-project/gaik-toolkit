/**
 * Baseline security response headers (#133).
 *
 * The deployed app previously sent none of these — measured against the Rahti
 * staging deploy on 26 Aug 2026, which returned only `x-powered-by`,
 * `cache-control` and `content-type`.
 *
 * Lives here rather than inline in next.config.ts so the policy is testable
 * and the config stays thin.
 *
 * The Content-Security-Policy is not here. It carries a per-request nonce, so
 * the proxy (proxy.ts) sets it (lib/csp.ts) on every request it sees; a second,
 * static CSP from next.config.ts would be intersected with it by the browser.
 * The routes the proxy's matcher leaves out get their own static policy,
 * `JSON_ROUTE_CSP`, from next.config.ts.
 */
export function buildSecurityHeaders() {
  return [
    // No Strict-Transport-Security here on purpose. It is set at the OpenShift
    // route instead (haproxy.router.openshift.io/hsts_header), which also covers
    // the router's own error pages — a response the app never gets to emit. Two
    // sources for one header would only drift apart.
    // Clickjacking. The CSP's `frame-ancestors` is the modern equivalent; both
    // are set because older browsers ignore the CSP directive.
    { key: "X-Frame-Options", value: "DENY" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  ] as const;
}

export const securityHeaders = buildSecurityHeaders();
