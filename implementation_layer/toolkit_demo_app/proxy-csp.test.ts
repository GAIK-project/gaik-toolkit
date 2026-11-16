import { expect, test } from "bun:test";
import { NextRequest } from "next/server";
import proxy from "./proxy";

// No request here reaches Supabase or the backend: a malformed path is refused
// first, and a page without a session cookie makes no auth call.

const nonceIn = (csp: string | null) => /'nonce-([^']+)'/.exec(csp ?? "")?.[1];

test("a page gets a nonce policy, and the renderer the same policy", async () => {
  const response = await proxy(new NextRequest("https://demo.test/parser"));
  const csp = response.headers.get("content-security-policy");
  expect(nonceIn(csp)).toBeTruthy();
  expect(csp).not.toContain("unsafe-eval");
  // NextResponse.next({ request }) hands the request headers on like this.
  expect(
    response.headers.get("x-middleware-request-content-security-policy"),
  ).toBe(csp);
});

test("a refused page path carries the policy too, with a new nonce each time", async () => {
  const bad = () => proxy(new NextRequest("https://demo.test/x//y"));
  const first = await bad();
  const second = await bad();
  expect(first.status).toBe(404);
  const a = nonceIn(first.headers.get("content-security-policy"));
  const b = nonceIn(second.headers.get("content-security-policy"));
  expect(a).toBeTruthy();
  expect(a).not.toBe(b);
});

test("an API response keeps the base policy from the config", async () => {
  const response = await proxy(new NextRequest("https://demo.test/api//x"));
  expect(response.status).toBe(404);
  expect(response.headers.get("content-security-policy")).toBeNull();
});
