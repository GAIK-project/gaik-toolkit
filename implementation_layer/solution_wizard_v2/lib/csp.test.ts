import { describe, expect, it } from "vitest";
import { buildCsp, JSON_ROUTE_CSP, makeNonce } from "./csp";

const directive = (csp: string, name: string) =>
  csp.split("; ").find((d) => d.startsWith(`${name} `));

describe("the per-request Content-Security-Policy", () => {
  it("makes a fresh base64 nonce of 128 bits", () => {
    const a = makeNonce();
    const b = makeNonce();
    expect(a).toMatch(/^[A-Za-z0-9+/]{22}==$/);
    expect(a).not.toBe(b);
  });

  it("allows scripts by nonce, never inline", () => {
    const csp = buildCsp({ nonce: "abc123", nodeEnv: "production" });
    const scriptSrc = directive(csp, "script-src");
    expect(scriptSrc).toBe("script-src 'self' 'nonce-abc123' 'strict-dynamic'");
    expect(scriptSrc).not.toContain("'unsafe-inline'");
  });

  it("allows eval only for the development server, never in production (T6)", () => {
    expect(directive(buildCsp({ nonce: "n", nodeEnv: "development" }), "script-src")).toBe(
      "script-src 'self' 'nonce-n' 'strict-dynamic' 'unsafe-eval'",
    );
    expect(buildCsp({ nonce: "n", nodeEnv: "production" })).not.toContain("'unsafe-eval'");
    expect(buildCsp({ nonce: "n", nodeEnv: "test" })).not.toContain("'unsafe-eval'");
  });

  // bpmn-js and React Flow set element styles directly on the canvas.
  it("keeps inline styles allowed for the diagram canvases", () => {
    expect(directive(buildCsp({ nonce: "n" }), "style-src")).toBe("style-src 'self' 'unsafe-inline'");
  });

  it("confines everything else to the same origin, as before", () => {
    const csp = buildCsp({ nonce: "n", nodeEnv: "production" });
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("img-src 'self' data: blob:");
    expect(csp).toContain("font-src 'self' data:");
    expect(csp).toContain("connect-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain("object-src 'none'");
  });

  it("lets the upload routes, which answer JSON, load nothing at all", () => {
    expect(JSON_ROUTE_CSP).toContain("default-src 'none'");
    expect(JSON_ROUTE_CSP).toContain("frame-ancestors 'none'");
  });
});
