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

const user: Record<string, string> = {
  id: "u1",
  aud: "authenticated",
  role: "authenticated",
};

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
let backendHeaders: Headers | null = null;
// The signed-in user's access_requests row.
let accessRow = { status: "approved", wizard_access: false };

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
      return Response.json(accessRow);
    backendCalls += 1;
    backendHeaders = new Headers(init?.headers);
    if (url.includes("/unreachable"))
      throw new TypeError("fetch failed: connect ECONNREFUSED 10.1.2.3:8000");
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
  backendHeaders = null;
  delete user.email;
  accessRow = { status: "approved", wizard_access: false };
});

const expired = () => Math.floor(Date.now() / 1000) - 60;

function run(cookie: string) {
  return proxy(new NextRequest(RUN, { method: "POST", headers: { cookie } }));
}

test("a POST from a visitor who is not signed in is refused before the backend", async () => {
  const response = await proxy(new NextRequest(RUN, { method: "POST" }));
  expect(response.status).toBe(401);
  expect(await response.json()).toEqual({
    error: "Sign in to use this feature.",
  });
  expect(backendCalls).toBe(0);
});

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

// The access rules match the path the backend routes on, so an encoded letter
// cannot move a request from one rule to another.

const fresh = () => Math.floor(Date.now() / 1000) + 3600;

function post(url: string, init: { cookie?: string; ownKey?: boolean } = {}) {
  const headers = new Headers();
  if (init.cookie) headers.set("cookie", init.cookie);
  if (init.ownKey) headers.set("x-gaik-model-settings", "e30");
  return proxy(new NextRequest(url, { method: "POST", headers }));
}

// The first Solution Wizard's agent has shell tools, so its API has a gate of
// its own: the per-user wizard_access grant, for reads as well as writes.

test("a wizard request without the grant is refused before the backend", async () => {
  // A signed-in, approved user, also holding the old team cookie and key.
  const savedSecret = process.env.WIZARD_ACCESS_SECRET;
  process.env.WIZARD_ACCESS_SECRET = "team-key";
  try {
    const cookie = `${sessionCookie("r1", fresh())}; wizard_access=team-key`;
    for (const path of ["/api/wizard/start", "/api/%77izard/start"]) {
      const response = await post(`https://demo.test${path}`, { cookie });
      expect(response.status).toBe(403);
      expect(await response.json()).toEqual({
        error:
          "The first wizard in the browser needs access from the GAIK team.",
      });
    }
    const read = await proxy(
      new NextRequest("https://demo.test/api/wizard/files/abc", {
        headers: { cookie },
      }),
    );
    expect(read.status).toBe(403);
  } finally {
    if (savedSecret === undefined) delete process.env.WIZARD_ACCESS_SECRET;
    else process.env.WIZARD_ACCESS_SECRET = savedSecret;
  }
  expect(backendCalls).toBe(0);
});

test("a wizard request from a visitor who is not signed in is refused", async () => {
  const start = await post("https://demo.test/api/wizard/start");
  expect(start.status).toBe(401);
  const read = await proxy(
    new NextRequest("https://demo.test/api/wizard/download/abc"),
  );
  expect(read.status).toBe(401);
  expect(backendCalls).toBe(0);
});

test("a granted user's wizard request is forwarded with the user's id", async () => {
  accessRow = { status: "approved", wizard_access: true };
  const cookie = sessionCookie("r1", fresh());
  const start = await proxy(
    new NextRequest("https://demo.test/api/wizard/start", {
      method: "POST",
      // What the browser claims is not passed on.
      headers: { cookie, "x-gaik-wizard-user": "someone-else" },
    }),
  );
  expect(start.status).toBe(200);
  expect(backendHeaders?.get("x-gaik-wizard-user")).toBe("u1");

  const read = await proxy(
    new NextRequest("https://demo.test/api/wizard/files/abc", {
      headers: { cookie, "x-gaik-wizard-user": "someone-else" },
    }),
  );
  expect(read.status).toBe(200);
  expect(backendHeaders?.get("x-gaik-wizard-user")).toBe("u1");
  expect(backendCalls).toBe(2);
});

test("the grant alone does not run the wizard for a user who is not approved", async () => {
  accessRow = { status: "rejected", wizard_access: true };
  const response = await post("https://demo.test/api/wizard/start", {
    cookie: sessionCookie("r1", fresh()),
  });
  expect(response.status).toBe(403);
  expect(backendCalls).toBe(0);
});

test("ending a wizard session spends no trial run", async () => {
  // A granted user still waiting for approval; the trial is off here (no Redis),
  // so a request that needed a trial run would be refused.
  accessRow = { status: "pending", wizard_access: true };
  const cookie = sessionCookie("r1", fresh());
  const end = await proxy(
    new NextRequest("https://demo.test/api/wizard/end/abc", {
      method: "DELETE",
      headers: { cookie },
    }),
  );
  expect(end.status).toBe(200);
  const start = await post("https://demo.test/api/wizard/start", { cookie });
  expect(start.status).toBe(403);
  expect(backendCalls).toBe(1);
});

test("another route does not get the wizard's user header", async () => {
  accessRow = { status: "approved", wizard_access: true };
  const response = await post(RUN, { cookie: sessionCookie("r1", fresh()) });
  expect(response.status).toBe(200);
  expect(backendHeaders?.has("x-gaik-wizard-user")).toBe(false);
});

test("a path the rules cannot judge is not forwarded", async () => {
  const cookie = sessionCookie("r1", fresh());
  for (const path of ["/api//wizard/start", "/api/x%2F..%2Fwizard/start"]) {
    const response = await post(`https://demo.test${path}`, { cookie });
    expect(response.status).toBe(404);
  }
  expect(backendCalls).toBe(0);
});

test("a visitor with their own model key is asked to sign in", async () => {
  for (const path of [
    "/api/extract",
    "/api/postgres-agent/ask",
    "/api/%65xtract",
  ]) {
    const response = await post(`https://demo.test${path}`, { ownKey: true });
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({
      error: "Sign in to use this feature.",
    });
  }
  expect(backendCalls).toBe(0);
});

test("the API learns the model tier from the session, never from the browser", async () => {
  const cookie = sessionCookie("r1", fresh());
  const send = () =>
    proxy(
      new NextRequest("https://demo.test/api/extract", {
        method: "POST",
        headers: { cookie, "x-gaik-model-tier": "staff" },
      }),
    );

  // Signed in and approved, but not on the team: the browser's header is dropped.
  expect((await send()).status).toBe(200);
  expect(backendHeaders?.get("x-gaik-model-tier")).toBeNull();

  // On the team by address: the proxy says so.
  user.email = "someone@haaga-helia.fi";
  expect((await send()).status).toBe(200);
  expect(backendHeaders?.get("x-gaik-model-tier")).toBe("staff");
  expect(backendCalls).toBe(2);
});

test("a path that only begins like the wizard API meets the normal gate", async () => {
  const response = await proxy(
    new NextRequest("https://demo.test/api/wizardry/start", { method: "POST" }),
  );
  expect(response.status).toBe(401);
  expect(backendCalls).toBe(0);
});

test("an unreachable backend is reported with an id, not the connection error", async () => {
  const response = await proxy(
    new NextRequest("https://demo.test/api/unreachable", {
      headers: { cookie: sessionCookie("r1", fresh()) },
    }),
  );
  expect(response.status).toBe(502);
  const { error } = await response.json();
  expect(error).toContain("error id");
  expect(error).not.toContain("ECONNREFUSED");
  expect(error).not.toContain("10.1.2.3");
});

test("the generic proxy does not pass on the report run header", async () => {
  const future = Math.floor(Date.now() / 1000) + 3600;
  const response = await proxy(
    new NextRequest(RUN, {
      method: "POST",
      headers: {
        cookie: sessionCookie("r1", future),
        "x-gaik-report-run": "from-the-browser",
      },
    }),
  );
  expect(response.status).toBe(200);
  expect(backendCalls).toBe(1);
  expect(backendHeaders?.has("x-gaik-report-run")).toBe(false);
});
