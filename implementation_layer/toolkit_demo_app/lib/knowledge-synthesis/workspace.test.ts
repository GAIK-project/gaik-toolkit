import { afterEach, expect, test } from "bun:test";
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { zipWorkspace } from "@/lib/knowledge-curator/workspace";
import { putKnowledgeHandoff, takeKnowledgeHandoff } from "@/lib/knowledge-curator/handoff";
import {
  EXAMPLE_INSTRUCTIONS,
  EXAMPLE_SAMPLE,
  EXAMPLE_SAMPLE_NAME,
  EXAMPLE_SECTIONS,
  EXAMPLE_TITLE,
} from "./example";
import {
  assemble,
  buildRequest,
  checkSynthesizeForm,
  DEFAULT_OPTIONS,
  diagnose,
  isSampleFile,
  knowledgeId,
  MAX_SAMPLE_BYTES,
  parseResult,
  readKnowledgeZip,
  type SectionInput,
  writingOrder,
  zipReport,
} from "./workspace";

const s = (id: string, depends_on: string[] = [], title = id.toUpperCase()): SectionInput => ({
  id,
  title,
  instructions: "",
  required_items: [],
  depends_on,
});

// -- writing order --------------------------------------------------------------------

test("writingOrder puts curated sections first and each derived section after its prerequisites", () => {
  const sections = [s("summary", ["a", "b"]), s("a"), s("b"), s("recs", ["a", "summary"])];

  expect(writingOrder(sections)).toEqual([["a", "b"], ["summary"], ["recs"]]);
  expect(writingOrder([s("a"), s("b")])).toEqual([["a", "b"]]);
});

test("writingOrder is null for a cycle or an unknown dependency", () => {
  expect(writingOrder([s("a", ["b"]), s("b", ["a"])])).toBeNull();
  expect(writingOrder([s("a", ["a"])])).toBeNull();
  expect(writingOrder([s("a", ["missing"])])).toBeNull();
});

// -- diagnose -------------------------------------------------------------------------

test("diagnose accepts sections that match the knowledge", () => {
  const sections = [s("summary", ["a", "b"]), s("a"), s("b")];

  expect(diagnose(sections, ["a", "b"], 12)).toEqual([]);
});

test("diagnose names a section without knowledge and knowledge without a section", () => {
  const problems = diagnose([s("a"), s("b")], ["a", "orphan"], 12);

  expect(problems).toEqual([
    'No knowledge for "B". Curate it in the Knowledge Curator with the id "b", or make the section depend on other sections.',
    'The knowledge for "orphan" has no section. Add a section with the id "orphan".',
  ]);
});

test("diagnose refuses knowledge for a derived section", () => {
  const problems = diagnose([s("a"), s("sum", ["a"])], ["a", "sum"], 12);

  expect(problems).toHaveLength(1);
  expect(problems[0]).toContain('"sum" depends on other sections');
});

test("diagnose reports structural problems", () => {
  expect(diagnose([], [], 12)).toEqual(["Add at least one section, or load the example."]);
  expect(diagnose([s("a", [], " ")], ["a"], 12)).toContain("Every section needs a title.");
  expect(diagnose([s("a b")], ["a b"], 12).join(" ")).toContain("letters, digits");
  expect(diagnose([s("a"), s("a")], ["a"], 12)).toContain('Two sections have the id "a".');
  expect(diagnose([s("a"), s("b")], ["a", "b"], 1)).toContain("At most 1 sections.");
  expect(diagnose([s("a", ["zzz"])], [], 12)[0]).toContain("which is not a section");
  expect(diagnose([s("a", ["a"])], [], 12)[0]).toContain("cannot depend on itself");
  expect(diagnose([s("a", ["b"]), s("b", ["a"])], [], 12)).toContain(
    "The dependencies form a cycle: a section cannot wait for itself.",
  );
});

test("knowledgeId reads the section id from a knowledge path", () => {
  expect(knowledgeId("knowledge/roof_and-attic.json")).toBe("roof_and-attic");
});

test("the example fits the Knowledge Curator's own example", () => {
  // The curator example curates "ventilation" and "roof"; the summary is derived.
  expect(diagnose(EXAMPLE_SECTIONS, ["ventilation", "roof"], 12)).toEqual([]);
  expect(writingOrder(EXAMPLE_SECTIONS)).toEqual([["ventilation", "roof"], ["summary"]]);
  expect(EXAMPLE_TITLE && EXAMPLE_INSTRUCTIONS && EXAMPLE_SAMPLE.startsWith("# ")).toBeTruthy();
  expect(isSampleFile(EXAMPLE_SAMPLE_NAME)).toBe(true);
});

// -- request --------------------------------------------------------------------------

test("buildRequest trims text, drops blank required items and blank models", () => {
  const request = buildRequest(
    " Report ",
    "  ",
    " rules ",
    [{ ...s("a"), title: " A ", required_items: [" x ", "", " "] }],
    { ...DEFAULT_OPTIONS, writer_model: "  ", reviewer_model: " gpt-x ", citations: false },
  );

  expect(request.title).toBe("Report");
  expect(request.language).toBe("English");
  expect(request.instructions).toBe("rules");
  expect(request.sections[0]).toEqual({
    id: "a",
    title: "A",
    instructions: "",
    required_items: ["x"],
    depends_on: [],
  });
  expect(request.options).toMatchObject({
    writer_model: null,
    reviewer_model: "gpt-x",
    citations: false,
    docx: true,
  });
});

test("isSampleFile accepts the four sample types, ignoring case", () => {
  for (const name of ["a.md", "b.TXT", "c.docx", "d.PDF"]) expect(isSampleFile(name)).toBe(true);
  for (const name of ["a.png", "b.doc", "c", "d.md.exe"]) expect(isSampleFile(name)).toBe(false);
});

// -- form check -----------------------------------------------------------------------

const limits = { maxUploadMb: 1, maxSections: 3, maxEvidenceChars: 200, maxReviewAttempts: 5 };
const request = buildRequest("T", "English", "", [s("a")], DEFAULT_OPTIONS);
const knowledge = { "knowledge/a.json": '{"section_id":"a"}' };

function form(req: unknown, artifacts: unknown = knowledge, sample?: File): FormData {
  const f = new FormData();
  if (req !== undefined) f.append("request", typeof req === "string" ? req : JSON.stringify(req));
  if (artifacts !== null)
    f.append("artifacts", new Blob([JSON.stringify(artifacts)]), "artifacts.json");
  if (sample) f.append("sample_report", sample, sample.name);
  return f;
}

test("checkSynthesizeForm accepts a valid request, with and without a sample report", async () => {
  expect(await checkSynthesizeForm(form(request), limits)).toBeNull();
  const sample = new File(["# Sample"], "sample.md");
  expect(await checkSynthesizeForm(form(request, knowledge, sample), limits)).toBeNull();
});

test("checkSynthesizeForm refuses malformed requests", async () => {
  const many = { ...request, sections: Array(4).fill(s("a")) };
  const attempts = { ...request, options: { ...DEFAULT_OPTIONS, review_attempts: 6 } };
  const err = async (f: FormData) => (await checkSynthesizeForm(f, limits))?.error;

  expect(await err(form(undefined))).toBe("Missing request.");
  expect(await err(form("{"))).toBe("Invalid request JSON.");
  expect(await err(form({ sections: [] }))).toContain("no sections");
  expect(await err(form(many))).toContain("Too many sections");
  expect(await err(form(attempts))).toContain("Too many review attempts");
  expect(await err(form(request, null))).toContain("must be a file");
  expect(await err(form(request, {}))).toContain("Curate knowledge in the Knowledge Curator first");
  expect(await err(form(request, { "normalized/a.md": "x" }))).toContain("Unknown artifact path");
});

test("checkSynthesizeForm enforces the knowledge, sample and upload limits", async () => {
  const long = { "knowledge/a.json": "x".repeat(201) };
  expect(await checkSynthesizeForm(form(request, long), limits)).toEqual({
    status: 413,
    error: "The knowledge holds 201 characters, over the 200 limit.",
  });
  const badType = new File(["x"], "sample.exe");
  expect((await checkSynthesizeForm(form(request, knowledge, badType), limits))?.error).toContain(
    "must be one of",
  );
  const big = new File([new Uint8Array(MAX_SAMPLE_BYTES + 1)], "sample.pdf");
  expect((await checkSynthesizeForm(form(request, knowledge, big), limits))?.error).toBe(
    "The sample report is over 1 MB.",
  );
});

// -- result ---------------------------------------------------------------------------

const RESULT = {
  title: "T",
  markdown: "# T\n\n## A\n\nText.\n",
  sections: [{ id: "a", title: "A", text: "Text." }],
  review_log: [{ section_id: "a", applied: [{ search: "x", replace: "y", reason: "r" }], unresolved: [] }],
  usage: { total_tokens: 5 },
  docx_b64: null,
};

test("parseResult accepts a result, defaults the docx fields, and rejects a malformed one", () => {
  const parsed = parseResult(RESULT);

  expect(parsed.docx_b64).toBeNull();
  expect(parsed.docx_error).toBeNull();
  expect(parsed.sections).toEqual(RESULT.sections);
  expect(() => parseResult({ ...RESULT, sections: [{ id: 1 }] })).toThrow("malformed");
  expect(() => parseResult({ ...RESULT, usage: undefined })).toThrow("malformed");
  expect(() => parseResult(null)).toThrow("malformed");
});

test("assemble writes the report as gaik does", () => {
  expect(assemble("T", [{ id: "a", title: "A", text: "Edited.\n" }, { id: "b", title: "B", text: "Two." }])).toBe(
    "# T\n\n## A\n\nEdited.\n\n## B\n\nTwo.\n",
  );
  expect(assemble("T", RESULT.sections)).toBe(RESULT.markdown);
});

test("zipReport holds the report, the sections, the review log and the docx", () => {
  const files = unzipSync(zipReport("T", RESULT.sections, RESULT.review_log, new Uint8Array([1, 2])));

  expect(Object.keys(files).sort()).toEqual(["report.docx", "report.md", "review_log.json", "sections/01_a.md"]);
  expect(strFromU8(files["report.md"])).toBe(RESULT.markdown);
  expect(strFromU8(files["sections/01_a.md"])).toBe("## A\n\nText.\n");
  expect(JSON.parse(strFromU8(files["review_log.json"]))[0].applied[0].reason).toBe("r");
  expect(Object.keys(unzipSync(zipReport("T", RESULT.sections, [], null)))).not.toContain("report.docx");
});

// -- knowledge zip ----------------------------------------------------------------------

test("readKnowledgeZip reads the knowledge of a Knowledge Curator zip and ignores the sources", () => {
  const normalized = {
    "normalized/sources.json": "[]",
    "normalized/01_a.md": "text",
  };
  const zip = zipWorkspace(normalized, knowledge);

  expect(readKnowledgeZip(zip)).toEqual(knowledge);
  expect(readKnowledgeZip(zipSync({ "knowledge/a.json": strToU8('{"section_id":"a"}') }))).toEqual(knowledge);
});

test("readKnowledgeZip rejects zips without knowledge and invalid zips", () => {
  expect(() => readKnowledgeZip(zipSync({ "normalized/a.md": strToU8("x") }))).toThrow(
    "downloaded from the Knowledge Curator",
  );
  expect(() => readKnowledgeZip(strToU8("not a zip"))).toThrow("not a valid .zip");
  expect(() => readKnowledgeZip(new Uint8Array(21 * 1024 * 1024))).toThrow("over 20 MB");
});

// -- hand-off from the curator ----------------------------------------------------------

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

test("the knowledge hand-off is stored, read once and then gone", () => {
  const data = fakeStorage();

  expect(putKnowledgeHandoff(knowledge)).toBe(true);
  expect(takeKnowledgeHandoff()).toEqual(knowledge);
  expect(takeKnowledgeHandoff()).toBeNull();
  expect(data.size).toBe(0);
});

test("the knowledge hand-off reports a full storage and ignores corrupt or empty data", () => {
  expect(fakeStorage(true) && putKnowledgeHandoff(knowledge)).toBe(false);

  const data = fakeStorage();
  data.set("gaik:knowledge-handoff", "{not json");
  expect(takeKnowledgeHandoff()).toBeNull();
  data.set("gaik:knowledge-handoff", JSON.stringify({ "normalized/a.md": "x" }));
  expect(takeKnowledgeHandoff()).toBeNull();
  data.set("gaik:knowledge-handoff", "{}");
  expect(takeKnowledgeHandoff()).toBeNull();
  expect(data.size).toBe(0);
});
