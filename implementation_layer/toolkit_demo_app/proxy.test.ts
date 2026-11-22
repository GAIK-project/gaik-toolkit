import { afterAll, beforeAll, beforeEach, expect, test } from "bun:test";
import { NextRequest, type NextResponse } from "next/server";
import {
  EMAIL_UNCONFIRMED,
  PENDING_DENIAL,
  SHARED_DATA_DENIAL,
} from "./lib/api-access";
import { createAdminSessionValue } from "./lib/admin/session";

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
  "UPSTASH_REDIS_REST_URL",
  "UPSTASH_REDIS_REST_TOKEN",
] as const;
const saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]]));
const realFetch = globalThis.fetch;
process.env.BYPASS_AUTH = "";
// No trial store: a pending user's run that needs a trial run is refused.
delete process.env.UPSTASH_REDIS_REST_URL;
delete process.env.UPSTASH_REDIS_REST_TOKEN;
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

// Analytics requests are rewritten to PostHog (next.config.ts) and carry this
// site's cookies. The proxy hands them on without the Cookie header and leaves
// the session alone.

/** The request headers Next.js forwards after the proxy, or null for none set. */
function forwarded(response: NextResponse): Map<string, string> | null {
  const names = response.headers.get("x-middleware-override-headers");
  if (names === null) return null;
  return new Map(
    names
      .split(",")
      .filter(Boolean)
      .map((name) => [
        name,
        response.headers.get(`x-middleware-request-${name}`) ?? "",
      ]),
  );
}

test("an analytics request goes on without this site's cookies", async () => {
  const cookie = [
    sessionCookie("r1", expired()),
    "admin_session=signed-admin-value",
    "wizard_access=team-secret",
  ].join("; ");
  for (const [method, path] of [
    ["POST", "/a/e/?ip=1"],
    ["POST", "/a/i/v0/e/"],
    ["GET", "/a/static/array.js"],
    ["POST", "/A/flags/?v=2"],
    ["GET", "/a"],
  ]) {
    const response = await proxy(
      new NextRequest(`https://demo.test${path}`, {
        method,
        headers: { cookie, "user-agent": "test-agent" },
      }),
    );
    const headers = forwarded(response);
    expect(headers?.get("user-agent")).toBe("test-agent");
    expect(headers?.has("cookie")).toBe(false);
    expect(response.cookies.getAll()).toEqual([]);
  }
  // The expired session was neither refreshed nor read.
  expect(refreshes).toEqual([]);
  expect(backendCalls).toBe(0);
});

test("a page request keeps its cookies for the app", async () => {
  const cookie = sessionCookie("r1", fresh());
  const response = await proxy(
    new NextRequest("https://demo.test/extractor", { headers: { cookie } }),
  );
  expect(forwarded(response)?.get("cookie")).toBe(cookie);
});

// The access rules match the path the backend routes on, so an encoded letter
// cannot move a request from one rule to another.

const fresh = () => Math.floor(Date.now() / 1000) + 3600;

// A well-formed own-key header, which the proxy re-encodes and forwards.
const OWN_KEY = JSON.stringify({
  provider: "openai",
  model: "test-model",
  apiKey: "test-key",
});

function post(url: string, init: { cookie?: string; ownKey?: boolean } = {}) {
  const headers = new Headers();
  if (init.cookie) headers.set("cookie", init.cookie);
  if (init.ownKey) headers.set("x-gaik-model-settings", OWN_KEY);
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

test("a signed-in user's request names the user, never the browser's claim", async () => {
  const cookie = sessionCookie("r1", fresh());
  const runResponse = await proxy(
    new NextRequest(RUN, {
      method: "POST",
      headers: { cookie, "x-gaik-user": "someone-else" },
    }),
  );
  expect(runResponse.status).toBe(200);
  expect(backendHeaders?.get("x-gaik-user")).toBe("u1");

  const download = await proxy(
    new NextRequest("https://demo.test/api/pipeline/pdf/abc", {
      headers: { cookie, "x-gaik-user": "someone-else" },
    }),
  );
  expect(download.status).toBe(200);
  expect(backendHeaders?.get("x-gaik-user")).toBe("u1");
});

test("a read that hands out no result names no user", async () => {
  const cookie = sessionCookie("r1", fresh());
  const read = await proxy(
    new NextRequest("https://demo.test/api/tabular-agent/status", {
      headers: { cookie },
    }),
  );
  expect(read.status).toBe(200);
  expect(backendHeaders?.has("x-gaik-user")).toBe(false);
});

test("a visitor who is not signed in names no user, whatever the browser sends", async () => {
  const download = await proxy(
    new NextRequest("https://demo.test/api/pipeline/pdf/abc", {
      headers: { "x-gaik-user": "u1" },
    }),
  );
  expect(download.status).toBe(200);
  expect(backendHeaders?.has("x-gaik-user")).toBe(false);
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

const OWN_KEY_RUN = "https://demo.test/api/extract";

test("a visitor whose refresh token is spent and who sends their own model key is asked to sign in", async () => {
  // The first request spends the refresh token; the second cannot refresh the
  // session, so it is anonymous.
  await run(sessionCookie("r1", expired()));
  backendCalls = 0;
  const response = await post(OWN_KEY_RUN, {
    cookie: sessionCookie("r1", expired()),
    ownKey: true,
  });
  expect(response.status).toBe(401);
  expect(backendCalls).toBe(0);
});

test("an approved user runs on their own model key, and the key reaches the API", async () => {
  const response = await post(OWN_KEY_RUN, {
    cookie: sessionCookie("r1", fresh()),
    ownKey: true,
  });
  expect(response.status).toBe(200);
  expect(backendCalls).toBe(1);
  expect(
    JSON.parse(backendHeaders?.get("x-gaik-model-settings") ?? "null"),
  ).toEqual(JSON.parse(OWN_KEY));
});

test("a pending user with a confirmed e-mail address runs on their own model key without a trial run", async () => {
  // No trial store is configured in these tests, so a run that needed a trial
  // run would be refused: the own-key run passes without one.
  accessRow = { status: "pending", wizard_access: false };
  user.email_confirmed_at = "2026-01-01T00:00:00Z";
  try {
    const cookie = sessionCookie("r1", fresh());
    const trial = await post(OWN_KEY_RUN, { cookie });
    expect(trial.status).toBe(403);
    expect(backendCalls).toBe(0);
    const ownKey = await post(OWN_KEY_RUN, { cookie, ownKey: true });
    expect(ownKey.status).toBe(200);
    expect(backendCalls).toBe(1);
  } finally {
    delete user.email_confirmed_at;
  }
});

test("a pending user without a confirmed e-mail address is refused with their own model key", async () => {
  accessRow = { status: "pending", wizard_access: false };
  const response = await post(OWN_KEY_RUN, {
    cookie: sessionCookie("r1", fresh()),
    ownKey: true,
  });
  expect(response.status).toBe(403);
  expect(await response.json()).toEqual({ error: EMAIL_UNCONFIRMED.error });
  expect(backendCalls).toBe(0);
});

test("a rejected user is refused with their own model key", async () => {
  accessRow = { status: "rejected", wizard_access: false };
  user.email_confirmed_at = "2026-01-01T00:00:00Z";
  try {
    const response = await post(OWN_KEY_RUN, {
      cookie: sessionCookie("r1", fresh()),
      ownKey: true,
    });
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: PENDING_DENIAL.error });
    expect(backendCalls).toBe(0);
  } finally {
    delete user.email_confirmed_at;
  }
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

test("the picked reasoning effort reaches the API only as low, medium or high", async () => {
  const cookie = sessionCookie("r1", fresh());
  const forwarded = async (url: string, effort: string, ownKey = false) => {
    const response = await proxy(
      new NextRequest(url, {
        method: "POST",
        headers: {
          cookie,
          "x-gaik-reasoning-effort": effort,
          ...(ownKey ? { "x-gaik-model-settings": OWN_KEY } : {}),
        },
      }),
    );
    expect(response.status).toBe(200);
    return backendHeaders?.get("x-gaik-reasoning-effort") ?? null;
  };

  expect(await forwarded("https://demo.test/api/extract", "high")).toBe("high");
  // With an own key as well.
  expect(await forwarded(OWN_KEY_RUN, "low", true)).toBe("low");
  for (const value of ["none", "max", "HIGH", "high, low"])
    expect(await forwarded("https://demo.test/api/extract", value)).toBeNull();
  // A route that takes no picked model gets no effort either.
  expect(
    await forwarded("https://demo.test/api/tabular-agent/ask", "high"),
  ).toBeNull();
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

// A user waiting for approval runs demos on the trial, which never covers a
// write to the video-search index that every visitor searches (nor does
// approval: that takes the admin session, tested below). Without Redis the
// trial is off here and this user's e-mail address is unconfirmed, so the
// refusal is told apart by its reason; that it holds with trial runs left is in
// lib/api-access.test.ts.

test("a pending user's DELETE /api/video-search/clear is refused", async () => {
  accessRow = { status: "pending", wizard_access: false };
  const cookie = sessionCookie("r1", fresh());
  const requests = [
    ...[
      "/api/video-search/clear",
      "/api/video-search/%63lear",
      "/api/video-search/clear/",
    ].map(
      (path) =>
        new NextRequest(`https://demo.test${path}`, {
          method: "DELETE",
          headers: { cookie },
        }),
    ),
    new NextRequest("https://demo.test/api/video-search/ingest/stream", {
      method: "POST",
      headers: { cookie },
    }),
  ];
  for (const request of requests) {
    const response = await proxy(request);
    expect(response.status).toBe(SHARED_DATA_DENIAL.status);
    expect(await response.json()).toEqual({ error: SHARED_DATA_DENIAL.error });
  }
  expect(backendCalls).toBe(0);
});

test("an approved user's write to the shared video index needs the admin session", async () => {
  const savedSecret = process.env.ADMIN_SESSION_SECRET;
  process.env.ADMIN_SESSION_SECRET = "test-admin-key";
  try {
    const session = sessionCookie("r1", fresh());
    const clear = (cookie: string) =>
      proxy(
        new NextRequest("https://demo.test/api/video-search/clear", {
          method: "DELETE",
          headers: { cookie },
        }),
      );
    for (const cookie of [session, `${session}; admin_session=authenticated`]) {
      const refused = await clear(cookie);
      expect(refused.status).toBe(SHARED_DATA_DENIAL.status);
      expect(await refused.json()).toEqual({ error: SHARED_DATA_DENIAL.error });
    }
    expect(backendCalls).toBe(0);

    const admin = await clear(
      `${session}; admin_session=${createAdminSessionValue()}`,
    );
    expect(admin.status).toBe(200);
    expect(backendCalls).toBe(1);
  } finally {
    if (savedSecret === undefined) delete process.env.ADMIN_SESSION_SECRET;
    else process.env.ADMIN_SESSION_SECRET = savedSecret;
  }
});

test("a video's playback link is handed out to a signed-in user only", async () => {
  for (const path of [
    "/api/video-search/videos/v1/play",
    "/api/video-search/videos/v1/thumbnail",
    "/api/video-search/%76ideos/v1/play",
  ]) {
    const anonymous = await proxy(
      new NextRequest(`https://demo.test${path}`, {
        headers: { "x-gaik-signed-in": "1" },
      }),
    );
    expect(anonymous.status).toBe(401);
  }
  expect(backendCalls).toBe(0);

  accessRow = { status: "pending", wizard_access: false };
  const signedIn = await proxy(
    new NextRequest("https://demo.test/api/video-search/videos/v1/play", {
      headers: { cookie: sessionCookie("r1", fresh()) },
    }),
  );
  expect(signedIn.status).toBe(200);
  expect(backendHeaders?.get("x-gaik-signed-in")).toBe("1");

  // An open read does not carry the header, whatever the browser sends.
  const list = await proxy(
    new NextRequest("https://demo.test/api/video-search/videos", {
      headers: { "x-gaik-signed-in": "1" },
    }),
  );
  expect(list.status).toBe(200);
  expect(backendHeaders?.has("x-gaik-signed-in")).toBe(false);
  expect(backendCalls).toBe(2);
});

// Upload limits (lib/upload-limits.ts): /api/parse takes 22 MiB in all. A body
// is refused by its declared length before any of it is read, and otherwise at
// the first chunk past the limit; the backend sees neither.

const MIB = 1024 * 1024;

function upload(chunks: number, size: number, declared?: number) {
  const seen = { pulled: 0 };
  const body = new ReadableStream<Uint8Array>(
    {
      pull(controller) {
        if (seen.pulled === chunks) return controller.close();
        seen.pulled += 1;
        controller.enqueue(new Uint8Array(size));
      },
    },
    { highWaterMark: 0 },
  );
  const headers = new Headers({
    cookie: sessionCookie("r1", fresh()),
    "content-type": "multipart/form-data; boundary=x",
  });
  if (declared !== undefined) headers.set("content-length", String(declared));
  const request = new NextRequest("https://demo.test/api/parse", {
    method: "POST",
    headers,
    body,
    duplex: "half",
  } as ConstructorParameters<typeof NextRequest>[1]);
  return { request, seen };
}

test("an upload that declares more than its route takes is refused before it is read", async () => {
  const { request, seen } = upload(30, MIB, 30 * MIB);
  const response = await proxy(request);
  expect(response.status).toBe(413);
  expect(await response.json()).toEqual({
    error: "File too large. Maximum size is 20MB",
    detail: "File too large. Maximum size is 20MB",
  });
  expect(seen.pulled).toBe(0);
  expect(backendCalls).toBe(0);
});

test("an upload without a declared length is refused once it passes its route's limit", async () => {
  const { request, seen } = upload(30, MIB);
  const response = await proxy(request);
  expect(response.status).toBe(413);
  expect(seen.pulled).toBe(23);
  expect(backendCalls).toBe(0);
});

test("an upload within its route's limit is forwarded whole", async () => {
  const { request } = upload(3, MIB);
  const response = await proxy(request);
  expect(response.status).toBe(200);
  expect(backendCalls).toBe(1);
  expect(backendHeaders?.get("content-length")).toBe(String(3 * MIB));
});
