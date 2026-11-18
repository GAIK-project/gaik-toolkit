import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/session-access", () => ({
  requireOwnedSession: vi.fn(async () => ({ user: { email: "dev@gaik.local" }, session: {} })),
}));
vi.mock("@/lib/wizard-api-client", () => ({
  wizardApiEnabled: vi.fn(() => true),
  apiGetPocFile: vi.fn(),
  apiPutPocFile: vi.fn(),
}));
vi.mock("@/lib/audit", () => ({ audit: vi.fn() }));
vi.mock("@/lib/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/i18n")>();
  return { ...actual, getI18n: async () => ({ locale: "en", t: actual.dictionary("en") }) };
});

import { GET, PUT } from "@/app/api/sessions/[id]/poc/file/route";
import { audit } from "@/lib/audit";
import { resetMockSessions } from "@/lib/mock-sessions";
import { MAX_POC_FILE_BYTES } from "@/lib/poc-file";
import { requireOwnedSession } from "@/lib/session-access";
import { apiGetPocFile, apiPutPocFile, wizardApiEnabled } from "@/lib/wizard-api-client";

const TRACE = "trace-file-0001";
const params = { params: Promise.resolve({ id: "s1" }) };
const url = (path: string) => `http://localhost/api/sessions/s1/poc/file?path=${encodeURIComponent(path)}`;

const get = (path: string) => GET(new NextRequest(url(path), { headers: { "x-trace-id": TRACE } }), params);

function put(path: string, body: unknown, headers: Record<string, string> = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return PUT(
    new NextRequest(url(path), {
      method: "PUT",
      headers: {
        "x-trace-id": TRACE,
        "content-type": "application/json",
        "content-length": String(Buffer.byteLength(text)),
        ...headers,
      },
      body: text,
    }),
    params,
  );
}

const refusal = (status: number, error: string, message: string) =>
  Response.json({ detail: { error, message } }, { status });

describe("PoC file relay", () => {
  beforeEach(() => {
    vi.mocked(apiGetPocFile).mockReset();
    vi.mocked(apiPutPocFile).mockReset();
    vi.mocked(audit).mockReset();
    vi.mocked(wizardApiEnabled).mockReturnValue(true);
    vi.mocked(requireOwnedSession).mockResolvedValue({
      user: { email: "dev@gaik.local" },
      session: {},
    } as Awaited<ReturnType<typeof requireOwnedSession>>);
  });

  it("answers 404 for a session that is not the caller's, without asking the api", async () => {
    vi.mocked(requireOwnedSession).mockResolvedValue(null);

    expect((await get("run_poc.py")).status).toBe(404);
    expect((await put("run_poc.py", { content: "x", base_digest: "d" })).status).toBe(404);
    expect(apiGetPocFile).not.toHaveBeenCalled();
    expect(apiPutPocFile).not.toHaveBeenCalled();
  });

  it("relays a file as the api answered it, uncached", async () => {
    vi.mocked(apiGetPocFile).mockResolvedValue(
      Response.json({ path: "run_poc.py", content: "print('ok')\n", digest: "d1", editable: true }),
    );

    const res = await get("run_poc.py");

    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect((await res.json()).content).toBe("print('ok')\n");
    expect(apiGetPocFile).toHaveBeenCalledWith("s1", "run_poc.py");
  });

  it.each([
    [422, "secrets_not_stored"],
    [422, "invalid_path"],
    [415, "file_not_text"],
    [413, "file_too_large"],
    [404, "not_found"],
  ])("passes a refused read on with its status and code (%i %s)", async (status, code) => {
    vi.mocked(apiGetPocFile).mockResolvedValue(refusal(status, code, "the api's own words"));

    const res = await get(".env");

    expect(res.status).toBe(status);
    expect((await res.json()).detail).toMatchObject({ error: code, message: "the api's own words" });
  });

  it.each([
    [409, "file_changed"],
    [409, "wizard_responding"],
    [403, "file_read_only"],
    [422, "file_type_not_editable"],
  ])("passes a refused save on with its status and code (%i %s)", async (status, code) => {
    vi.mocked(apiPutPocFile).mockResolvedValue(refusal(status, code, "the api's own words"));

    const res = await put("run_poc.py", { content: "x", base_digest: "d1" });

    expect(res.status).toBe(status);
    expect((await res.json()).detail.error).toBe(code);
    expect(audit).toHaveBeenCalledWith("poc.file.save", expect.objectContaining({ outcome: "error" }));
  });

  it("passes a key given a value in .env.example on with the variables it names", async () => {
    vi.mocked(apiPutPocFile).mockResolvedValue(
      Response.json(
        {
          detail: {
            error: "key_value_not_stored",
            message: "a key's value is not kept on the server",
            variables: ["AZURE_API_KEY"],
            trace_id: TRACE,
          },
        },
        { status: 422 },
      ),
    );

    const res = await put(".env.example", { content: "AZURE_API_KEY=\n", base_digest: "d1" });

    expect(res.status).toBe(422);
    expect((await res.json()).detail).toMatchObject({ error: "key_value_not_stored", variables: ["AZURE_API_KEY"] });
  });

  it("does not pass on an error it does not know, or a server path in one", async () => {
    vi.mocked(apiPutPocFile).mockResolvedValue(
      refusal(500, "OSError", "[Errno 13] Permission denied: '/data/sessions/abc/poc/run_poc.py'"),
    );

    const res = await put("run_poc.py", { content: "x", base_digest: "d1" });
    const text = await res.text();

    expect(text).not.toContain("/data/sessions");
    expect(JSON.parse(text).detail).toMatchObject({ error: "internal_error", trace_id: TRACE });
  });

  it("saves through the api and audits the file's name, not its content", async () => {
    vi.mocked(apiPutPocFile).mockResolvedValue(
      Response.json({ path: "run_poc.py", digest: "d2", gate_reopened: null, affects_package: true }),
    );

    const res = await put("run_poc.py", { content: "print('edited')\n", base_digest: "d1" });

    expect(res.status).toBe(200);
    expect((await res.json()).digest).toBe("d2");
    expect(apiPutPocFile).toHaveBeenCalledWith("s1", "run_poc.py", "print('edited')\n", "d1");
    expect(audit).toHaveBeenCalledWith(
      "poc.file.save",
      expect.objectContaining({ outcome: "success", action: "run_poc.py" }),
    );
    expect(JSON.stringify(vi.mocked(audit).mock.calls)).not.toContain("edited");
  });

  it("refuses a body that is too large, says no length, or is not the two fields", async () => {
    const tooLong = await put("run_poc.py", { content: "x".repeat(MAX_POC_FILE_BYTES + 1), base_digest: "d1" });
    expect(tooLong.status).toBe(413);
    expect((await tooLong.json()).detail.error).toBe("file_too_large");

    const declared = await put("run_poc.py", { content: "x", base_digest: "d1" }, { "content-length": "99999999" });
    expect(declared.status).toBe(413);

    const noLength = await PUT(
      new NextRequest(url("run_poc.py"), { method: "PUT", body: JSON.stringify({ content: "x", base_digest: "d" }) }),
      params,
    );
    expect(noLength.status).toBe(411);

    expect((await put("run_poc.py", { content: 1, base_digest: "d1" })).status).toBe(400);
    expect((await put("run_poc.py", { content: "x" })).status).toBe(400);
    expect((await put("run_poc.py", "not json")).status).toBe(400);
    expect((await put("", { content: "x", base_digest: "d1" })).status).toBe(422);
    expect(apiPutPocFile).not.toHaveBeenCalled();
  });

  describe("without wizard_api (the mock store)", () => {
    beforeEach(() => {
      vi.mocked(wizardApiEnabled).mockReturnValue(false);
      resetMockSessions();
    });

    it("reads, saves and refuses as the api does", async () => {
      const read = await (await get("run_poc.py")).json();
      expect(read).toMatchObject({ path: "run_poc.py", editable: true, affects_package: true });

      const saved = await put("run_poc.py", { content: "print('mine')\n", base_digest: read.digest });
      expect(saved.status).toBe(200);
      expect((await (await get("run_poc.py")).json()).content).toBe("print('mine')\n");

      // The digest it was read with is no longer the file's.
      const stale = await put("run_poc.py", { content: "print('late')\n", base_digest: read.digest });
      expect(stale.status).toBe(409);
      expect((await stale.json()).detail.error).toBe("file_changed");
      // A refused save is audited here as it is with wizard_api.
      expect(audit).toHaveBeenLastCalledWith("poc.file.save", expect.objectContaining({ outcome: "error" }));

      for (const path of [".env", "config/.env.local", "prod.env"]) {
        const refused = await get(path);
        expect(refused.status).toBe(422);
        expect((await refused.json()).detail.error).toBe("secrets_not_stored");
      }
      expect((await get("../outside.txt")).status).toBe(422);
      expect((await get("missing.py")).status).toBe(404);
      expect((await put("AI-GENERATED.json", { content: "{}", base_digest: "d" })).status).toBe(403);
      expect((await put("sample_input/note.txt", { content: "x", base_digest: "d" })).status).toBe(403);
      expect(apiGetPocFile).not.toHaveBeenCalled();
    });

    it("refuses a key's value in .env.example, and says which file a test run is tied to", async () => {
      const read = await (await get(".env.example")).json();
      expect(read.affects_package).toBe(true);
      expect((await (await get("README.md")).json()).affects_package).toBe(false);

      const refused = await put(".env.example", {
        content: `${read.content}TAVILY_API_KEY=typed-by-mistake\n`,
        base_digest: read.digest,
      });

      expect(refused.status).toBe(422);
      const detail = (await refused.json()).detail;
      expect(detail).toMatchObject({ error: "key_value_not_stored", variables: ["TAVILY_API_KEY"] });
      expect(JSON.stringify(detail)).not.toContain("typed-by-mistake");
      expect((await (await get(".env.example")).json()).content).toBe(read.content);
      // Without a value the variable is saved.
      const saved = await put(".env.example", {
        content: `${read.content}TAVILY_API_KEY=\n`,
        base_digest: read.digest,
      });
      expect(saved.status).toBe(200);
    });
  });
});
