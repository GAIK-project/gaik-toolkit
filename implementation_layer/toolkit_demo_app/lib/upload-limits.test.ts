import { expect, test } from "bun:test";
import { REPORT_REQUEST_MAX_BYTES } from "./report-writer/upload-limit";
import {
  DEFAULT_LIMIT,
  bodyLimitFor,
  readBodyWithin,
  readFormWithin,
} from "./upload-limits";

const MIB = 1024 * 1024;

/** A request whose body arrives in `chunks` pieces of `size` bytes; counts the pieces read. */
function streamed(chunks: number, size: number, declared?: number) {
  const seen = { pulled: 0, cancelled: false };
  const body = new ReadableStream<Uint8Array>(
    {
      pull(controller) {
        if (seen.pulled === chunks) return controller.close();
        seen.pulled += 1;
        controller.enqueue(new Uint8Array(size).fill(120));
      },
      cancel() {
        seen.cancelled = true;
      },
    },
    { highWaterMark: 0 },
  );
  const headers = new Headers({ "content-type": "application/octet-stream" });
  if (declared !== undefined) headers.set("content-length", String(declared));
  const request = new Request("https://demo.test/api/parse", {
    method: "POST",
    headers,
    body,
    duplex: "half",
  } as RequestInit);
  return { request, seen };
}

test("routes are looked up by their API path, a '/' entry by prefix", () => {
  expect(bodyLimitFor("/parse").maxBytes).toBe(22 * MIB);
  expect(bodyLimitFor("/transcribe").maxFiles).toBe(1);
  expect(bodyLimitFor("/wizard/message/abc").maxBytes).toBe(68 * MIB);
  expect(bodyLimitFor("/rag/query")).toBe(DEFAULT_LIMIT);
  expect(DEFAULT_LIMIT.maxFiles).toBe(0);
});

test("the report runs keep the request cap their pages are told about", () => {
  for (const path of [
    "/report-writer/run",
    "/report-writer-v2/run",
    "/source-normalizer/run",
    "/knowledge-curator/run",
    "/knowledge-synthesis/run",
  ])
    expect(bodyLimitFor(path).maxBytes).toBe(REPORT_REQUEST_MAX_BYTES);
});

test("a body that declares more than the limit is refused before any of it is read", async () => {
  const { request, seen } = streamed(10, 100, 1000);
  expect(await readBodyWithin(request, 999)).toBeNull();
  expect(seen.pulled).toBe(0);
});

test("a body without a declared length is refused at the first chunk past the limit", async () => {
  const { request, seen } = streamed(100, 100);
  expect(await readBodyWithin(request, 950)).toBeNull();
  expect(seen.pulled).toBe(10);
  expect(seen.cancelled).toBe(true);
});

test("a body that carries more than it declared is refused at the limit too", async () => {
  const { request, seen } = streamed(100, 100, 500);
  expect(await readBodyWithin(request, 950)).toBeNull();
  expect(seen.pulled).toBeLessThan(100);
});

test("a body within the limit is read whole", async () => {
  const { request } = streamed(5, 100, 500);
  const body = await readBodyWithin(request, 500);
  expect(body?.byteLength).toBe(500);
  expect(new Uint8Array(body!).every((b) => b === 120)).toBe(true);
});

function form(files: number): Request {
  const data = new FormData();
  data.append("config", "{}");
  for (let i = 0; i < files; i++)
    data.append("files", new File(["text"], `f${i}.txt`));
  return new Request("https://demo.test/api/report-writer/run", {
    method: "POST",
    body: data,
  });
}

test("a form with more files than the route takes is refused", async () => {
  expect(await readFormWithin(form(3), { maxBytes: MIB, maxFiles: 2 })).toEqual(
    {
      ok: false,
      status: 400,
      error: "Too many files: at most 2 files per request.",
    },
  );
});

test("a form within the limits is parsed", async () => {
  const read = await readFormWithin(form(2), { maxBytes: MIB, maxFiles: 2 });
  expect(read.ok).toBe(true);
  if (read.ok) expect(read.form.getAll("files")).toHaveLength(2);
});

test("a form over the size limit is refused as too large", async () => {
  expect(await readFormWithin(form(2), { maxBytes: 100, maxFiles: 2 })).toEqual(
    { ok: false, status: 413 },
  );
});

test("a body that is not form data is refused", async () => {
  const request = new Request("https://demo.test/api/report-writer/run", {
    method: "POST",
    headers: { "content-type": "multipart/form-data; boundary=x" },
    body: "not a form",
  });
  expect(await readFormWithin(request, { maxBytes: MIB, maxFiles: 2 })).toEqual(
    { ok: false, status: 400, error: "Invalid form data." },
  );
});
