import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// PoC generation answers as SSE log lines; what the api said goes into those lines.
vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" }, session: {} })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiGeneratePoc: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { POST } from "@/app/api/sessions/[id]/poc/route";
import { dictionary } from "@/lib/i18n";
import { apiGeneratePoc } from "@/lib/wizard-api-client";

const TRACE = "trace-poc-00001";
const en = dictionary("en");

async function lines(): Promise<{ logs: string[]; status: string }> {
  const req = new NextRequest("http://localhost/api/sessions/s1/poc", {
    method: "POST",
    headers: { "x-trace-id": TRACE },
  });
  const res = await POST(req, { params: Promise.resolve({ id: "s1" }) });
  const frames = (await res.text())
    .split("\n\n")
    .filter((f) => f.startsWith("data: "))
    .map((f) => JSON.parse(f.slice(6)));
  return {
    logs: frames.filter((f) => typeof f.log === "string").map((f) => f.log),
    status: frames.find((f) => f.done)?.status,
  };
}

describe("PoC generation relay", () => {
  beforeEach(() => {
    vi.mocked(apiGeneratePoc).mockReset();
  });

  it("says why the api refused, for a known code", async () => {
    vi.mocked(apiGeneratePoc).mockResolvedValue(
      Response.json(
        { detail: { error: "gate_not_approved", gate: "gate_2", message: "approve Gate 2 before generating the PoC package" } },
        { status: 409 },
      ),
    );
    const { logs, status } = await lines();
    expect(status).toBe("failed");
    expect(logs).toEqual([en.pocLogFailed, "approve Gate 2 before generating the PoC package"]);
  });

  it("does not show a scaffolder error with a server path and a traceback", async () => {
    vi.mocked(apiGeneratePoc).mockResolvedValue(
      Response.json(
        { detail: 'scaffolding failed: Traceback (most recent call last): File "/srv/wizard/out/abc/poc/run.py"' },
        { status: 503 },
      ),
    );
    const { logs } = await lines();
    expect(logs.join("\n")).not.toContain("/srv/wizard");
    expect(logs.join("\n")).not.toContain("Traceback");
    expect(logs).toEqual([en.pocLogFailed, en.errorGeneric.replace("{trace}", TRACE)]);
  });

  it("does not show the text of an error thrown on the way to the api", async () => {
    vi.mocked(apiGeneratePoc).mockImplementation(async () => {
      throw new Error("fetch failed: getaddrinfo ENOTFOUND wizard-api.internal");
    });
    const { logs } = await lines();
    expect(logs.join("\n")).not.toContain("wizard-api.internal");
    expect(logs).toEqual([en.pocLogFailed, en.errorUnreachable.replace("{trace}", TRACE)]);
  });
});
