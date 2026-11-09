import { expect, test } from "bun:test";
import nextConfig from "./next.config";
import { securityHeaders } from "./lib/security-headers";

const value = (key: string) =>
  securityHeaders.find((h) => h.key === key)?.value;

test("every path gets the security headers", async () => {
  const rules = await nextConfig.headers!();
  expect(rules).toEqual([{ source: "/:path*", headers: securityHeaders }]);
});

test("framing is same-origin only, so the PDF previews keep working", () => {
  expect(value("X-Frame-Options")).toBe("SAMEORIGIN");
  expect(value("Content-Security-Policy")).toContain("frame-ancestors 'self'");
});

test("HSTS stays on this host: the router domain is shared", () => {
  expect(value("Strict-Transport-Security")).not.toContain("includeSubDomains");
});

test("the framework name is not announced", () => {
  expect(nextConfig.poweredByHeader).toBe(false);
});
