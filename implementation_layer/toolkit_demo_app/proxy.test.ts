import { afterAll, beforeAll, beforeEach, expect, test } from "bun:test";
import { NextRequest, type NextResponse } from "next/server";

// A demo run from a page left open past the access token's lifetime: the API
// gate refreshes the session, and the browser must get the new cookies, or its
// next run spends the old refresh token again and is refused as signed out.
// Supabase and the backend are faked with a fetch stub; no module mocks.

const SUPABASE_URL = "https://demo-ref.supabase.co";
const COOKIE = "sb-demo-ref-auth-token";
const RUN = "https://demo.test/api/luvata-order/custom/schema";

const KEYS = [
  "BYPASS_AUTH",
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
] as const;
const saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]]));
const realFetch = globalThis.fetch;
process.env.BYPASS_AUTH = "";
const { default: proxy } = await import("./proxy");

function jwt(sub: string, exp: number): string {
  const part = (o: object) =>
    Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${part({ alg: "HS256", typ: "JWT" })}.${part({ sub, exp, role: "authenticated" })}.sig`;
}

const user = { id: "u1", aud: "authenticated", role: "authenticated" };

function session(refreshToken: string, expiresAt: number) {
  return {
    access_token: jwt("u1", expiresAt),
    token_type: "bearer",
    expires_in: 3600,
    expires_at: expiresAt,
    refresh_token: refreshToken,
    user,
  };
}

function sessionCookie(refreshToken: string, expiresAt: number): string {
  const value = Buffer.from(
    JSON.stringify(session(refreshToken, expiresAt)),
  ).toString("base64url");
  return `${COOKIE}=base64-${value}`;
}

function refreshTokenIn(response: NextResponse): string | null {
  const value = response.cookies.get(COOKIE)?.value;
  if (!value) return null;
  return JSON.parse(
    Buffer.from(value.replace(/^base64-/, ""), "base64url").toString(),
  ).refresh_token;
}

let refreshes: string[] = [];
let backendCalls = 0;

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = SUPABASE_URL;
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    if (url.startsWith(`${SUPABASE_URL}/auth/v1/token`)) {
      const body = JSON.parse(String(init?.body ?? "{}"));
      refreshes.push(body.refresh_token);
      // A refresh token works once (outside Supabase's short reuse window).
      if (body.refresh_token !== "r1" || refreshes.length > 1)
        return Response.json(
          {
            code: 400,
            error_code: "refresh_token_already_used",
            msg: "Invalid Refresh Token: Already Used",
          },
          { status: 400 },
        );
      return Response.json(session("r2", Math.floor(Date.now() / 1000) + 3600));
    }
    if (url.startsWith(`${SUPABASE_URL}/auth/v1/user`))
      return Response.json(user);
    if (url.startsWith(`${SUPABASE_URL}/rest/v1/access_requests`))
      return Response.json({ status: "approved", wizard_access: false });
    backendCalls += 1;
    return Response.json({ ok: true });
  }) as typeof fetch;
});

afterAll(() => {
  globalThis.fetch = realFetch;
  for (const k of KEYS)
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
});

beforeEach(() => {
  refreshes = [];
  backendCalls = 0;
});

const expired = () => Math.floor(Date.now() / 1000) - 60;

function run(cookie: string) {
  return proxy(new NextRequest(RUN, { method: "POST", headers: { cookie } }));
}

test("a run on an expired session saves the refreshed session", async () => {
  const first = await run(sessionCookie("r1", expired()));
  expect(first.status).toBe(200);
  expect(refreshTokenIn(first)).toBe("r2");

  // The browser sends what it was given: the next run needs no refresh.
  const cookie = first.cookies
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  const second = await run(cookie);
  expect(second.status).toBe(200);
  expect(refreshes).toEqual(["r1"]);
  expect(backendCalls).toBe(2);
});

test("a spent refresh token is refused and the dead session cleared", async () => {
  await run(sessionCookie("r1", expired()));
  const again = await run(sessionCookie("r1", expired()));
  expect(again.status).toBe(401);
  expect(await again.json()).toEqual({ error: "Sign in to use this feature." });
  expect(again.cookies.get(COOKIE)?.value).toBe("");
  expect(backendCalls).toBe(1);
});
