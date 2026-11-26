import { afterAll, beforeAll, expect, test } from "bun:test";
import { NextRequest } from "next/server";
import { createAdminSessionValue } from "./lib/admin/session";
import proxy from "./proxy";

// Maintenance mode as the proxy applies it (lib/maintenance.ts). The backend
// is a fetch stub that counts its calls: nothing may reach it while the mode
// is on, the health check included.

const KEYS = [
  "DEMO_MAINTENANCE",
  "ADMIN_SESSION_SECRET",
  "BYPASS_AUTH",
] as const;
const saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]]));
const realFetch = globalThis.fetch;
let backendCalls = 0;

beforeAll(() => {
  process.env.DEMO_MAINTENANCE = "on";
  process.env.ADMIN_SESSION_SECRET = "test-admin-key";
  process.env.BYPASS_AUTH = "";
  globalThis.fetch = (async () => {
    backendCalls += 1;
    return Response.json({ status: "ok" });
  }) as unknown as typeof fetch;
});

afterAll(() => {
  globalThis.fetch = realFetch;
  for (const k of KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

const call = (path: string, init: { method?: string; cookie?: string } = {}) =>
  proxy(
    new NextRequest(`https://demo.test${path}`, {
      method: init.method ?? "GET",
      headers: init.cookie ? { cookie: init.cookie } : {},
    }),
  );

test("a page gets the maintenance page, with the page policy", async () => {
  const res = await call("/extract");
  expect(res.status).toBe(503);
  expect(await res.text()).toContain("Palvelussa on huoltokatko");
  expect(res.headers.get("content-security-policy")).toContain("nonce-");
});

test("an API call and a report run get 503 before any other check", async () => {
  const before = backendCalls;
  for (const path of ["/api/extract/run", "/api/report-writer/run"]) {
    const res = await call(path, { method: "POST" });
    expect(res.status).toBe(503);
    expect(res.headers.get("x-demo-maintenance")).toBe("on");
  }
  expect(backendCalls).toBe(before);
});

test("the health check answers without the backend", async () => {
  const before = backendCalls;
  const res = await call("/api/health");
  expect(res.status).toBe(200);
  expect(await res.json()).toEqual({ status: "maintenance" });
  expect(backendCalls).toBe(before);
});

test("an admin session gets past the break", async () => {
  const res = await call("/api/health", {
    cookie: `admin_session=${createAdminSessionValue()}`,
  });
  // The admin is not stopped by the mode; the health check still is answered
  // here, so the pod stays up either way.
  expect(res.status).toBe(200);
  const page = await call("/extract", {
    cookie: `admin_session=${createAdminSessionValue()}`,
  });
  expect(page.status).not.toBe(503);
});

test("a forged admin cookie does not", async () => {
  const res = await call("/extract", { cookie: "admin_session=1.abc.forged" });
  expect(res.status).toBe(503);
});

test("the admin sign-in stays open", async () => {
  const res = await call("/admin");
  expect(res.status).not.toBe(503);
});
