import { afterEach, expect, test } from "bun:test";
import { strToU8, unzipSync, zipSync } from "fflate";
import { putHandoff, takeHandoff } from "@/lib/source-normalizer/handoff";
import {
  MANIFEST_PATH,
  parseArtifacts as parseNormalized,
  readManifest,
  zipArtifacts,
} from "@/lib/source-normalizer/workspace";
import { EXAMPLE_NORMALIZED, EXAMPLE_SECTIONS } from "./example";
import {
  buildRequest,
  checkCurateForm,
  DEFAULT_OPTIONS,
  MAX_ZIP_BYTES,
  parseKnowledge,
  readKnowledge,
  readWorkspaceZip,
  sectionsProblem,
  zipWorkspace,
} from "./workspace";

const limits = {
  maxUploadMb: 1,
  maxSections: 3,
  maxEvidenceChars: 100,
  maxCuratorWorkers: 4,
};
const section = { id: "a", title: "A", instructions: "", required_items: [] };
const request = { sections: [section], instructions: "", options: DEFAULT_OPTIONS };
const small = {
  [MANIFEST_PATH]: JSON.stringify([
    { id: "01_a", file: "a.txt", source_class: "primary", source_type: "text", tool: "text" },
  ]),
  "normalized/01_a.md": "Some text",
};

function form(req: unknown, artifacts: unknown = small): FormData {
  const f = new FormData();
  if (req !== undefined) f.append("request", typeof req === "string" ? req : JSON.stringify(req));
  if (artifacts !== null)
    f.append("artifacts", new Blob([JSON.stringify(artifacts)]), "artifacts.json");
  return f;
}

test("buildRequest trims text, drops blank required items and blank models", () => {
  const built = buildRequest(
    [{ id: "a", title: " A ", instructions: " x ", required_items: [" one ", "", "  "] }],
    "  rules ",
    { model: "  ", reasoning_effort: "low", max_workers: 2 },
  );

  expect(built).toEqual({
    sections: [{ id: "a", title: "A", instructions: "x", required_items: ["one"] }],
    instructions: "rules",
    options: { model: null, reasoning_effort: "low", max_workers: 2 },
  });
});

test("sectionsProblem names the first problem", () => {
  const ok = { ...section };

  expect(sectionsProblem([ok], 3)).toBeNull();
  expect(sectionsProblem([], 3)).toBe("Add at least one topic.");
  expect(sectionsProblem([ok, { ...ok, id: "b" }, { ...ok, id: "c" }, { ...ok, id: "d" }], 3)).toBe(
    "At most 3 topics.",
  );
  expect(sectionsProblem([{ ...ok, title: " " }], 3)).toBe("Every topic needs a title.");
  expect(sectionsProblem([{ ...ok, id: "has space" }], 3)).toContain("letters, digits");
  expect(sectionsProblem([ok, { ...ok, title: "B" }], 3)).toBe('Two topics have the id "a".');
});

test("checkCurateForm accepts a valid request", async () => {
  expect(await checkCurateForm(form(request), limits)).toBeNull();
});

test("checkCurateForm refuses malformed requests", async () => {
  const many = { ...request, sections: Array(4).fill(section) };
  const workers = { ...request, options: { ...DEFAULT_OPTIONS, max_workers: 5 } };

  expect((await checkCurateForm(form(undefined), limits))?.error).toBe("Missing request.");
  expect((await checkCurateForm(form("{"), limits))?.error).toBe("Invalid request JSON.");
  expect((await checkCurateForm(form({ sections: [] }), limits))?.error).toContain("no topics");
  expect((await checkCurateForm(form(many), limits))?.error).toContain("Too many topics");
  expect((await checkCurateForm(form(workers), limits))?.error).toContain("parallel");
  expect((await checkCurateForm(form(request, null), limits))?.error).toContain("must be a file");
  expect((await checkCurateForm(form(request, { "knowledge/x.json": "{}" }), limits))?.status).toBe(400);
  expect((await checkCurateForm(form(request, { "normalized/01_a.md": "x" }), limits))?.error).toContain(
    "sources.json",
  );
});

test("checkCurateForm enforces the evidence and upload limits", async () => {
  const long = { ...small, "normalized/01_a.md": "x".repeat(101) };

  expect(await checkCurateForm(form(request, long), limits)).toEqual({
    status: 413,
    error: "The normalized sources hold 101 characters, over the 100 limit.",
  });
  const big = { ...small, "normalized/01_a.md": "x".repeat(1024 * 1024) };
  expect((await checkCurateForm(form(request, big), { ...limits, maxEvidenceChars: 2e6 }))?.error).toBe(
    "Uploads exceed the 1 MB limit.",
  );
});

test("parseKnowledge and readKnowledge validate knowledge files", () => {
  const file = JSON.stringify({ section_id: "a", units: [], missing: [], conflicts: [] });

  expect(parseKnowledge({ "knowledge/a.json": file })).toEqual({ "knowledge/a.json": file });
  expect(() => parseKnowledge({ "normalized/a.md": "x" })).toThrow("Unknown artifact path");
  expect(() => parseKnowledge({ "knowledge/a.json": 1 })).toThrow("must be text");
  expect(readKnowledge(file).ok).toBe(true);
  expect(readKnowledge("{")).toMatchObject({ ok: false });
  expect(readKnowledge('{"section_id":"a"}')).toEqual({
    ok: false,
    error: "Expected section_id, units, missing and conflicts.",
  });
});

test("readWorkspaceZip reads the Source Normalizer zip with its normalized folder", () => {
  const zip = zipArtifacts(small);

  expect(readWorkspaceZip(zip)).toEqual({ normalized: small, knowledge: {} });
});

test("readWorkspaceZip reads top-level files and a demo workspace with knowledge", () => {
  const knowledge = { "knowledge/a.json": '{"section_id":"a"}' };
  const flat = zipSync({
    "sources.json": strToU8(small[MANIFEST_PATH]),
    "01_a.md": strToU8(small["normalized/01_a.md"]),
    "notes.txt": strToU8("ignored"),
  });
  const workspace = zipWorkspace(small, knowledge);

  expect(readWorkspaceZip(flat).normalized).toEqual(small);
  expect(readWorkspaceZip(workspace)).toEqual({ normalized: small, knowledge });
  expect(Object.keys(unzipSync(workspace)).sort()).toEqual([
    "knowledge/a.json",
    "normalized/01_a.md",
    MANIFEST_PATH,
  ]);
});

test("readWorkspaceZip rejects zips that are not normalized sources", () => {
  expect(() => readWorkspaceZip(strToU8("not a zip"))).toThrow("not a valid .zip");
  expect(() => readWorkspaceZip(zipSync({ "a.md": strToU8("x") }))).toThrow("No sources.json");
  expect(() => readWorkspaceZip(new Uint8Array(MAX_ZIP_BYTES + 1))).toThrow("over 20 MB");
});

test("the example is a valid normalized set and its sections are valid", () => {
  expect(parseNormalized(EXAMPLE_NORMALIZED)).toEqual(EXAMPLE_NORMALIZED);
  for (const entry of readManifest(EXAMPLE_NORMALIZED))
    expect(EXAMPLE_NORMALIZED[`normalized/${entry.id}.md`]).toBeTruthy();
  expect(sectionsProblem(EXAMPLE_SECTIONS, 12)).toBeNull();
});

// -- hand-off store: bun has no sessionStorage, so a Map-backed stand-in --

function fakeStorage(failOnSet = false) {
  const data = new Map<string, string>();
  (globalThis as { sessionStorage?: unknown }).sessionStorage = {
    getItem: (k: string) => data.get(k) ?? null,
    removeItem: (k: string) => void data.delete(k),
    setItem: (k: string, v: string) => {
      if (failOnSet) throw new Error("QuotaExceededError");
      data.set(k, v);
    },
  };
  return data;
}

afterEach(() => {
  delete (globalThis as { sessionStorage?: unknown }).sessionStorage;
});

test("the hand-off is stored, read once and then gone", () => {
  const data = fakeStorage();

  expect(putHandoff(small)).toBe(true);
  expect(takeHandoff()).toEqual(small);
  expect(takeHandoff()).toBeNull();
  expect(data.size).toBe(0);
});

test("the hand-off reports a full storage and ignores corrupt data", () => {
  expect(fakeStorage(true) && putHandoff(small)).toBe(false);

  const data = fakeStorage();
  data.set("gaik:normalized-handoff", "{not json");
  expect(takeHandoff()).toBeNull();
  data.set("gaik:normalized-handoff", JSON.stringify({ "knowledge/x.json": "{}" }));
  expect(takeHandoff()).toBeNull();
  expect(data.size).toBe(0);
});

test("takeHandoff is null where there is no storage", () => {
  expect(takeHandoff()).toBeNull();
});
