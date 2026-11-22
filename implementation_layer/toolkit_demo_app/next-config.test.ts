import { expect, test } from "bun:test";
import nextConfig from "./next.config";
import { isAnalyticsPath } from "./lib/analytics-path";
import { securityHeaders } from "./lib/security-headers";
import { LARGEST_LIMIT_BYTES } from "./lib/upload-limits";

const value = (key: string) =>
  securityHeaders.find((h) => h.key === key)?.value;

test("every path gets the security headers", async () => {
  const rules = await nextConfig.headers!();
  expect(rules).toEqual([{ source: "/:path*", headers: securityHeaders }]);
});

test("framing is same-origin only, so the PDF previews keep working", () => {
  // Pages get the same directive in their nonce policy too (lib/csp.ts).
  expect(value("X-Frame-Options")).toBe("SAMEORIGIN");
  expect(value("Content-Security-Policy")).toContain("frame-ancestors 'self'");
});

test("HSTS stays on this host: the router domain is shared", () => {
  expect(value("Strict-Transport-Security")).not.toContain("includeSubDomains");
});

test("the framework name is not announced", () => {
  expect(nextConfig.poweredByHeader).toBe(false);
});

test("every rewrite to another host is one the proxy strips cookies from", async () => {
  // The browser sends this site's cookies with these requests, and a rewrite
  // hands the request headers on to the other host.
  const rewrites = await nextConfig.rewrites!();
  const rules = Array.isArray(rewrites)
    ? rewrites
    : [
        ...(rewrites.beforeFiles ?? []),
        ...(rewrites.afterFiles ?? []),
        ...(rewrites.fallback ?? []),
      ];
  const external = rules.filter((rule) => /^https?:/i.test(rule.destination));
  expect(external.length).toBeGreaterThan(0);
  for (const rule of external) expect(isAnalyticsPath(rule.source)).toBe(true);
});

test("the proxy can read the largest body a route takes", () => {
  // Next.js copies a request body for the proxy only up to this size and cuts
  // it there; each route's own limit (lib/upload-limits.ts) is held below it.
  const size = String(nextConfig.experimental?.proxyClientMaxBodySize);
  const match = /^(\d+)mb$/.exec(size);
  expect(match).not.toBeNull();
  expect(Number(match![1]) * 1024 * 1024).toBeGreaterThanOrEqual(
    LARGEST_LIMIT_BYTES,
  );
});
