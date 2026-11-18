import { afterAll, expect, test } from "bun:test";
import { NextRequest } from "next/server";

// The five run routes refuse a body that declares more than the run takes
// before their gate runs, so the request reaches neither sign-in nor the trial
// count. Supabase is faked with a fetch stub that counts its calls; no module
// mocks.

const saved = process.env.BYPASS_AUTH;
process.env.BYPASS_AUTH = "";
const realFetch = globalThis.fetch;
let fetches = 0;
globalThis.fetch = (async () => {
  fetches += 1;
  return new Response("{}", { status: 500 });
}) as unknown as typeof fetch;

afterAll(() => {
  globalThis.fetch = realFetch;
  if (saved === undefined) delete process.env.BYPASS_AUTH;
  else process.env.BYPASS_AUTH = saved;
});

const ROUTES = [
  "report-writer",
  "report-writer-v2",
  "source-normalizer",
  "knowledge-curator",
  "knowledge-synthesis",
] as const;

for (const name of ROUTES) {
  test(`${name} run refuses a declared length over its limit before the gate`, async () => {
    const { POST } = await import(`./${name}/run/route`);
    fetches = 0;
    const request = new NextRequest(`https://demo.test/api/${name}/run`, {
      method: "POST",
      headers: {
        "content-type": "multipart/form-data; boundary=x",
        "content-length": String(200 * 1024 * 1024),
      },
      body: "--x--\r\n",
    });
    const response: Response = await POST(request);
    expect(response.status).toBe(413);
    expect((await response.json()).error).toContain("Uploads exceed the");
    expect(fetches).toBe(0);
  });
}
