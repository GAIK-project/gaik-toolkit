import { describe, expect, test } from "bun:test";
import { strFromU8, unzipSync } from "fflate";
import {
  DEFAULT_SETTINGS,
  FRESH,
  checkRunForm,
  classifyArtifact,
  groupArtifacts,
  knowledgeJsonError,
  parseArtifacts,
  parseSpec,
  staleAfterEdit,
  staleAfterStage,
  staleHint,
  stageReady,
  zipWorkspace,
  type ReportSpec,
} from "./workspace";

const SPEC: ReportSpec = {
  title: "Condition assessment",
  description: "d",
  language: "English",
  sections: [
    { id: "background", title: "Background", instructions: "i", required_items: ["year"], depends_on: [] },
    { id: "summary", title: "Summary", instructions: "i", required_items: [], depends_on: ["background"] },
  ],
  instructions: "",
  sources: { primary: ["rec1.mp3"], secondary: ["renovation_1998.pdf"] },
  sample_report: "sample_report.docx",
  models: { vision: null, transcription: null, curator: "c", writer: null, reviewer: null },
  settings: { ...DEFAULT_SETTINGS, writer: { reasoning_effort: "low", temperature: 0.2 } },
};

describe("parseSpec", () => {
  test("accepts the contract shape unchanged", () => {
    expect(parseSpec(JSON.parse(JSON.stringify(SPEC)))).toEqual(SPEC);
  });

  test("rejects unknown and missing keys", () => {
    expect(() => parseSpec({ ...SPEC, extra: 1 })).toThrow("spec has unknown keys extra");
    const { models: _, ...noModels } = SPEC;
    expect(() => parseSpec(noModels)).toThrow("spec is missing models");
    expect(() =>
      parseSpec({ ...SPEC, sections: [{ ...SPEC.sections[0], note: "x" }] }),
    ).toThrow("sections[0] has unknown keys note");
    expect(() => parseSpec({ ...SPEC, models: { ...SPEC.models, vision2: null } })).toThrow(
      "models has unknown keys vision2",
    );
    expect(() =>
      parseSpec({ ...SPEC, settings: { ...SPEC.settings, writer: { temperature: null } } }),
    ).toThrow("settings.writer is missing reasoning_effort");
  });

  test("rejects wrong types", () => {
    expect(() => parseSpec(null)).toThrow("spec must be an object");
    expect(() => parseSpec({ ...SPEC, title: 1 })).toThrow("title must be a string");
    expect(() =>
      parseSpec({ ...SPEC, sections: [{ ...SPEC.sections[0], depends_on: "x" }] }),
    ).toThrow("sections[0].depends_on must be an array of strings");
    expect(() => parseSpec({ ...SPEC, sources: { primary: [1], secondary: [] } })).toThrow(
      "sources.primary must be an array of strings",
    );
    expect(() => parseSpec({ ...SPEC, settings: { ...SPEC.settings, review_attempts: 0 } })).toThrow(
      "settings.review_attempts must be an integer of at least 1",
    );
    expect(() => parseSpec({ ...SPEC, settings: { ...SPEC.settings, docx: "yes" } })).toThrow(
      "settings.docx must be a boolean",
    );
    expect(() =>
      parseSpec({ ...SPEC, settings: { ...SPEC.settings, curator: { reasoning_effort: null, temperature: "0" } } }),
    ).toThrow("settings.curator.temperature must be a number or null");
  });
});

describe("artifact paths", () => {
  test("classifies every allowed path with its editable flag", () => {
    expect(classifyArtifact("normalized/01_rec1.md")).toEqual({ kind: "normalized", editable: false });
    expect(classifyArtifact("normalized/sources.json")).toEqual({ kind: "normalized", editable: false });
    expect(classifyArtifact("sample_report.md")).toEqual({ kind: "sample", editable: false });
    expect(classifyArtifact("knowledge/background.json")).toEqual({ kind: "knowledge", editable: true });
    expect(classifyArtifact("report/sections/01_background.md")).toEqual({ kind: "section", editable: true });
    expect(classifyArtifact("report/review_log.json")).toEqual({ kind: "review_log", editable: false });
    expect(classifyArtifact("report/report.md")).toEqual({ kind: "report", editable: false });
  });

  test("rejects paths outside the allowlist", () => {
    for (const p of [
      "report/report.docx",
      "knowledge/a.md",
      "normalized/sub/a.md",
      "../etc/passwd",
      "report/sections/a b.md",
      "sample_report.md.bak",
    ])
      expect(() => classifyArtifact(p)).toThrow(`Unknown artifact path "${p}".`);
  });

  test("parseArtifacts validates paths and text values", () => {
    expect(parseArtifacts({})).toEqual({});
    expect(parseArtifacts({ "report/report.md": "# R" })).toEqual({ "report/report.md": "# R" });
    expect(() => parseArtifacts([])).toThrow("Artifacts must be an object");
    expect(() => parseArtifacts({ "x.md": "" })).toThrow('Unknown artifact path "x.md".');
    expect(() => parseArtifacts({ "report/report.md": 1 })).toThrow("must be text");
  });

  test("groups folders in stage order with sorted paths", () => {
    expect(
      groupArtifacts([
        "sample_report.md",
        "report/sections/02_b.md",
        "report/report.md",
        "normalized/02_b.md",
        "normalized/01_a.md",
      ]),
    ).toEqual([
      { folder: "normalized", paths: ["normalized/01_a.md", "normalized/02_b.md"] },
      { folder: "report", paths: ["report/report.md", "report/sections/02_b.md"] },
      { folder: "", paths: ["sample_report.md"] },
    ]);
  });

  test("stageReady checks each stage's inputs", () => {
    const ws = { "normalized/01_a.md": "", "knowledge/a.json": "{}" };
    expect(stageReady("curate", {}, false)).toBe(false);
    expect(stageReady("curate", ws, false)).toBe(true);
    expect(stageReady("synthesize", ws, false)).toBe(true);
    expect(stageReady("synthesize", ws, true)).toBe(false);
    expect(stageReady("synthesize", { ...ws, "sample_report.md": "" }, true)).toBe(true);
    expect(stageReady("rebuild", ws, false)).toBe(false);
    expect(stageReady("rebuild", { "report/sections/01_a.md": "" }, false)).toBe(true);
  });

  test("knowledgeJsonError reports parse failures only", () => {
    expect(knowledgeJsonError('{"facts": []}')).toBeNull();
    expect(knowledgeJsonError("{facts: []}")).toBeString();
  });
});

describe("staleness", () => {
  test("a knowledge edit makes the report stale: Rerun Stage 3", () => {
    const s = staleAfterEdit(FRESH, "knowledge/a.json");
    expect(staleHint(s, "report/sections/01_a.md")).toBe("Rerun Stage 3");
    expect(staleHint(s, "report/report.docx")).toBe("Rerun Stage 3");
    expect(staleHint(s, "knowledge/a.json")).toBeNull();
    expect(s.editedSections).toBe(false);
  });

  test("a section edit makes report.md and the docx stale: Rebuild report", () => {
    const s = staleAfterEdit(FRESH, "report/sections/01_a.md");
    expect(staleHint(s, "report/report.md")).toBe("Rebuild report");
    expect(staleHint(s, "report/report.docx")).toBe("Rebuild report");
    expect(staleHint(s, "report/sections/01_a.md")).toBeNull();
    expect(staleHint(s, "report/review_log.json")).toBeNull();
    expect(s.editedSections).toBe(true);
  });

  test("view-only files cannot be edited", () => {
    expect(() => staleAfterEdit(FRESH, "report/report.md")).toThrow("not editable");
    expect(() => staleAfterEdit(FRESH, "normalized/01_a.md")).toThrow("not editable");
  });

  test("rerunning normalize marks knowledge and report; curate marks report", () => {
    const n = staleAfterStage(FRESH, "normalize");
    expect(staleHint(n, "knowledge/a.json")).toBe("Rerun Stage 2");
    expect(staleHint(n, "report/report.md")).toBe("Rerun Stage 3");
    expect(staleHint(n, "normalized/01_a.md")).toBeNull();
    const c = staleAfterStage(n, "curate");
    expect(staleHint(c, "knowledge/a.json")).toBeNull();
    expect(staleHint(c, "report/report.md")).toBe("Rerun Stage 3");
  });

  test("a successful stage clears its own staleness only", () => {
    const edited = staleAfterEdit(staleAfterStage(FRESH, "normalize"), "report/sections/01_a.md");
    expect(staleAfterStage(edited, "synthesize")).toEqual({ ...FRESH, knowledge: true });
    const rebuilt = staleAfterStage(staleAfterEdit(FRESH, "report/sections/01_a.md"), "rebuild");
    expect(rebuilt).toEqual({ ...FRESH, editedSections: true });
    expect(staleHint(rebuilt, "report/report.md")).toBeNull();
    const knowledgeEdited = staleAfterStage(staleAfterEdit(FRESH, "knowledge/a.json"), "rebuild");
    expect(staleHint(knowledgeEdited, "report/report.md")).toBe("Rerun Stage 3");
  });
});

describe("checkRunForm", () => {
  const LIMITS = {
    maxUploadMb: 1,
    maxSections: 2,
    maxEvidenceChars: 10,
    maxCuratorWorkers: 4,
    maxReviewAttempts: 5,
  };
  const form = (fields: Record<string, string | File | File[]>) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(fields))
      for (const item of Array.isArray(v) ? v : [v]) f.append(k, item);
    return f;
  };
  const ok = { spec: JSON.stringify(SPEC), artifacts: "{}" };
  const file = (name: string, size = 3) => new File(["x".repeat(size)], name);
  const uploads = {
    files: [file("rec1.mp3"), file("renovation_1998.pdf")],
    sample_report: file("sample_report.docx"),
  };

  test("accepts a valid request for each stage", () => {
    expect(checkRunForm(form({ ...ok, stage: "normalize", ...uploads }), LIMITS)).toBeNull();
    for (const stage of ["curate", "synthesize", "rebuild"])
      expect(checkRunForm(form({ ...ok, stage }), LIMITS)).toBeNull();
  });

  test("400 for a bad stage, spec, artifacts or section count", () => {
    const bad = (fields: Record<string, string | File | File[]>) => checkRunForm(form(fields), LIMITS);
    expect(bad({ ...ok, stage: "write" })).toEqual({ status: 400, error: 'Invalid stage "write".' });
    expect(bad({ artifacts: "{}", stage: "curate" })).toEqual({ status: 400, error: "Missing spec." });
    expect(bad({ ...ok, spec: "{", stage: "curate" })).toEqual({ status: 400, error: "Invalid spec JSON." });
    expect(bad({ ...ok, spec: "{}", stage: "curate" })?.error).toStartWith("Invalid spec: spec is missing");
    expect(bad({ spec: ok.spec, stage: "curate" })).toEqual({ status: 400, error: "Missing artifacts." });
    expect(bad({ ...ok, artifacts: "[", stage: "curate" })).toEqual({ status: 400, error: "Invalid artifacts JSON." });
    expect(bad({ ...ok, artifacts: '{"x.md":""}', stage: "curate" })).toEqual({
      status: 400,
      error: 'Unknown artifact path "x.md".',
    });
    const three = { ...SPEC, sections: [...SPEC.sections, { ...SPEC.sections[0], id: "c" }] };
    expect(bad({ ...ok, spec: JSON.stringify(three), stage: "curate" })).toEqual({
      status: 400,
      error: "Too many sections (max 2).",
    });
    const spec = (settings: object) => JSON.stringify({ ...SPEC, settings: { ...SPEC.settings, ...settings } });
    expect(bad({ ...ok, spec: spec({ curator_workers: 5 }), stage: "curate" })).toEqual({
      status: 400,
      error: "Too many parallel sections (max 4).",
    });
    expect(bad({ ...ok, spec: spec({ review_attempts: 6 }), stage: "synthesize" })).toEqual({
      status: 400,
      error: "Too many review attempts (max 5).",
    });
  });

  test("400 for files on the wrong stage or other than one per spec file on normalize", () => {
    const bad = (fields: Record<string, string | File | File[]>) =>
      checkRunForm(form({ ...ok, stage: "normalize", ...fields }), LIMITS);
    expect(bad({ sample_report: uploads.sample_report })).toEqual({
      status: 400,
      error: "Upload one file per spec source, in spec order: expected 2, got 0.",
    });
    expect(bad({ ...uploads, files: uploads.files.slice(1) })?.error).toEndWith("expected 2, got 1.");
    expect(bad({ files: uploads.files })).toEqual({
      status: 400,
      error: "Upload a sample_report exactly when the spec names one.",
    });
    expect(checkRunForm(form({ ...ok, stage: "curate", files: [file("a.pdf")] }), LIMITS)?.status).toBe(400);
    expect(checkRunForm(form({ ...ok, stage: "normalize", files: "a.pdf" }), LIMITS)?.status).toBe(400);
  });

  test("413 when files, sample and artifacts JSON exceed the upload limit", () => {
    const half = 512 * 1024;
    const r = checkRunForm(
      form({
        ...ok,
        stage: "normalize",
        files: [file("rec1.mp3", half), file("renovation_1998.pdf", 0)],
        sample_report: file("sample_report.docx", half - 2),
      }),
      LIMITS,
    );
    expect(r).toBeNull();
    const over = checkRunForm(
      form({
        ...ok,
        artifacts: JSON.stringify({ "normalized/01_a.md": "x" }),
        stage: "normalize",
        files: [file("rec1.mp3", half), file("renovation_1998.pdf", 0)],
        sample_report: file("sample_report.docx", half - 2),
      }),
      LIMITS,
    );
    expect(over).toEqual({ status: 413, error: "Uploads exceed the 1 MB limit." });
  });

  test("413 when curate evidence exceeds maxEvidenceChars; nothing else counts", () => {
    const arts = (md: string) =>
      JSON.stringify({ "normalized/01_a.md": md, "normalized/sources.json": "x".repeat(50), "sample_report.md": "x".repeat(50) });
    expect(checkRunForm(form({ ...ok, artifacts: arts("x".repeat(10)), stage: "curate" }), LIMITS)).toBeNull();
    expect(checkRunForm(form({ ...ok, artifacts: arts("x".repeat(11)), stage: "curate" }), LIMITS)).toEqual({
      status: 413,
      error: "The normalized sources hold 11 characters, over the 10 limit.",
    });
    expect(checkRunForm(form({ ...ok, artifacts: arts("x".repeat(11)), stage: "synthesize" }), LIMITS)).toBeNull();
  });
});

test("zipWorkspace stores every artifact at its path, plus the docx", () => {
  const docx = new Uint8Array([1, 2, 3]);
  const zip = unzipSync(zipWorkspace({ "report/report.md": "# R", "knowledge/a.json": "{}" }, docx));
  expect(Object.keys(zip).sort()).toEqual(["knowledge/a.json", "report/report.docx", "report/report.md"]);
  expect(strFromU8(zip["report/report.md"])).toBe("# R");
  expect(zip["report/report.docx"]).toEqual(docx);
  expect(Object.keys(unzipSync(zipWorkspace({}, null)))).toEqual([]);
});
