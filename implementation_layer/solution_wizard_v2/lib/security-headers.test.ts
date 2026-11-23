import { describe, expect, it } from "vitest";
import { securityHeaders } from "./security-headers";

const byKey = Object.fromEntries(securityHeaders.map((h) => [h.key, h.value]));

describe("security response headers (#133)", () => {
  it.each(["X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy"])(
    "sets %s",
    (key) => {
      expect(byKey[key]).toBeTruthy();
    },
  );

  it("blocks framing for older browsers; the CSP covers modern ones", () => {
    expect(byKey["X-Frame-Options"]).toBe("DENY");
  });

  it("leaves HSTS to the route, which also covers the router's error pages", () => {
    expect(byKey["Strict-Transport-Security"]).toBeUndefined();
  });

  // The CSP is per request (a nonce), so it comes from the middleware, never
  // from here: two CSP headers would be intersected by the browser.
  it("leaves the Content-Security-Policy to the middleware", () => {
    expect(byKey["Content-Security-Policy"]).toBeUndefined();
  });
});
