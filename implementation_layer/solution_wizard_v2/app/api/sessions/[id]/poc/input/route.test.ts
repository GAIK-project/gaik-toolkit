import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" } })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiListPocInputs: vi.fn(),
  apiUploadPocInput: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/poc/input/route";
import { apiUploadPocInput } from "@/lib/wizard-api-client";

const TRACE = "trace-input-001";

async function upload() {
  const form = new FormData();
  form.append("file", new File(["hello"], "invoice.pdf"), "invoice.pdf");
  // Encoded up front: the route refuses a body that does not say its length.
  const encoded = new Response(form);
  const body = await encoded.arrayBuffer();
  const req = new NextRequest("http://localhost/api/sessions/s1/poc/input", {
    method: "POST",
    headers: {
      "x-trace-id": TRACE,
      "content-type": encoded.headers.get("content-type") ?? "",
      "content-length": String(body.byteLength),
    },
    body,
  });
  return POST(req, { params: Promise.resolve({ id: "s1" }) });
}

describe("PoC input upload relay", () => {
  beforeEach(() => {
    vi.mocked(apiUploadPocInput).mockReset();
  });

  it("keeps the reason a file was refused", async () => {
    const detail = { error: "input_rejected", message: "'..' tries to leave the input directory", trace_id: TRACE };
    vi.mocked(apiUploadPocInput).mockResolvedValue(Response.json({ detail }, { status: 422 }));
    const res = await upload();
    expect(res.status).toBe(422);
    expect((await res.json()).detail).toEqual(detail);
  });

  it("turns an OS error with a server path into the generic message", async () => {
    vi.mocked(apiUploadPocInput).mockResolvedValue(
      Response.json(
        { detail: "OSError: [Errno 28] No space left on device: '/srv/wizard/out/abc/poc/sample_input'" },
        { status: 500 },
      ),
    );
    const res = await upload();
    const text = await res.text();
    expect(res.status).toBe(500);
    expect(text).not.toContain("/srv/wizard");
    expect(JSON.parse(text).detail).toMatchObject({ error: "internal_error", trace_id: TRACE });
  });
});
