import { expect, test } from "bun:test";
import { NextRequest, NextResponse } from "next/server";
import {
  ALLAS_ORIGIN,
  CSP_HEADER,
  BASE_CSP_DIRECTIVES,
  attachCsp,
  buildCsp,
  isPagePath,
  makeNonce,
  setCsp,
} from "./csp";

const directive = (csp: string, name: string) =>
  csp
    .split("; ")
    .find((d) => d.startsWith(`${name} `))
    ?.split(" ")
    .slice(1) ?? [];

test("scripts run only from this site, the nonce and what it loads", () => {
  const csp = buildCsp({ nonce: "abc", nodeEnv: "production" });
  expect(directive(csp, "script-src")).toEqual([
    "'self'",
    "'nonce-abc'",
    "'strict-dynamic'",
  ]);
  expect(csp).not.toContain("unsafe-eval");
  expect(directive(csp, "script-src")).not.toContain("'unsafe-inline'");
});

test("eval is allowed in development only", () => {
  const dev = buildCsp({ nonce: "abc", nodeEnv: "development" });
  expect(directive(dev, "script-src")).toContain("'unsafe-eval'");
});

test("framing stays same-origin and plugins and foreign bases are off", () => {
  const csp = buildCsp({ nonce: "abc", nodeEnv: "production" });
  expect(directive(csp, "frame-ancestors")).toEqual(["'self'"]);
  expect(directive(csp, "object-src")).toEqual(["'none'"]);
  expect(directive(csp, "base-uri")).toEqual(["'self'"]);
  expect(directive(csp, "form-action")).toEqual(["'self'"]);
});

test("the browser may call this site, Supabase and PostHog, nothing else by default", () => {
  const csp = buildCsp({
    nonce: "abc",
    nodeEnv: "production",
    supabaseUrl: "https://ref.supabase.co/",
    posthogHost: "https://eu.i.posthog.com",
    chatUrl: "",
  });
  expect(directive(csp, "connect-src")).toEqual([
    "'self'",
    "https://ref.supabase.co",
    "https://eu.i.posthog.com",
  ]);
  expect(directive(csp, "media-src")).toContain(ALLAS_ORIGIN);
});

test("a configured chat widget may connect and frame; a bad URL adds nothing", () => {
  const csp = buildCsp({
    nonce: "abc",
    nodeEnv: "production",
    supabaseUrl: "javascript:alert(1)",
    posthogHost: "",
    chatUrl: "https://chat.example/widget",
  });
  expect(directive(csp, "connect-src")).toEqual([
    "'self'",
    "https://chat.example",
  ]);
  for (const name of ["frame-src", "style-src", "font-src"])
    expect(directive(csp, name)).toContain("https://chat.example");
});

test("each nonce is fresh and 128 bits", () => {
  const a = makeNonce();
  expect(a).not.toBe(makeNonce());
  expect(atob(a)).toHaveLength(16);
});

test("the request carries the policy for the renderer; the response the same", () => {
  const request = new NextRequest("https://demo.test/parser");
  const csp = attachCsp(request, "production");
  expect(request.headers.get(CSP_HEADER)).toBe(csp);
  expect(csp).toMatch(/'nonce-[A-Za-z0-9+/=]{24}'/);
  const response = setCsp(NextResponse.next({ request }), csp);
  expect(response.headers.get(CSP_HEADER)).toBe(csp);
});

// Both policies reach a page; with each base directive repeated unchanged, the
// browser enforces the page policy and never a mix.
test("the page policy repeats every base directive unchanged", () => {
  const csp = buildCsp({ nonce: "abc", nodeEnv: "production" }).split("; ");
  for (const d of BASE_CSP_DIRECTIVES) expect(csp).toContain(d);
});

test("API paths, encoded ones too, and the PostHog rewrite are not pages", () => {
  expect(isPagePath("/parser")).toBe(true);
  expect(isPagePath("/")).toBe(true);
  expect(isPagePath("/about")).toBe(true);
  for (const path of [
    "/api/docs",
    "/api",
    "/%61pi/docs",
    "/a/e/",
    "/a",
    "/A/e/",
  ])
    expect(isPagePath(path)).toBe(false);
});
