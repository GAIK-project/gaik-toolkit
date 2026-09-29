// Knowledge Synthesis demo: the request and result contract shared by the page and its
// Next route, and the checks that tell the user what is wrong before a paid run.
// Pure functions only.
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { MAX_ZIP_BYTES, parseKnowledge } from "@/lib/knowledge-curator/workspace";
import type { ReportWriterLimits } from "@/lib/report-writer/limits";

export const MAX_SAMPLE_BYTES = 1024 * 1024;
export const SAMPLE_EXTENSIONS = [".md", ".txt", ".docx", ".pdf"] as const;
export const SAMPLE_ACCEPT = SAMPLE_EXTENSIONS.join(",");

export function isSampleFile(name: string): boolean {
  const dot = name.lastIndexOf(".");
  return (
    dot >= 0 &&
    (SAMPLE_EXTENSIONS as readonly string[]).includes(name.slice(dot).toLowerCase())
  );
}

export const EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"] as const;
export type Effort = (typeof EFFORTS)[number];

export interface SectionInput {
  id: string;
  title: string;
  instructions: string;
  required_items: string[];
  depends_on: string[];
}

export interface SynthOptions {
  writer_model: string | null;
  reviewer_model: string | null;
  writer_effort: Effort | null;
  reviewer_effort: Effort | null;
  review_attempts: number;
  strict_review: boolean;
  citations: boolean;
  docx: boolean;
}

export const DEFAULT_OPTIONS: SynthOptions = {
  writer_model: null,
  reviewer_model: null,
  writer_effort: null,
  reviewer_effort: null,
  review_attempts: 5,
  strict_review: false,
  citations: true,
  docx: true,
};

export interface SynthRequest {
  title: string;
  language: string;
  instructions: string;
  sections: SectionInput[];
  options: SynthOptions;
}

export function buildRequest(
  title: string,
  language: string,
  instructions: string,
  sections: SectionInput[],
  options: SynthOptions,
): SynthRequest {
  const clean = (v: string | null) => (v?.trim() ? v.trim() : null);
  return {
    title: title.trim(),
    language: language.trim() || "English",
    instructions: instructions.trim(),
    sections: sections.map((s) => ({
      id: s.id,
      title: s.title.trim(),
      instructions: s.instructions.trim(),
      required_items: s.required_items.map((x) => x.trim()).filter(Boolean),
      depends_on: s.depends_on,
    })),
    options: {
      ...options,
      writer_model: clean(options.writer_model),
      reviewer_model: clean(options.reviewer_model),
    },
  };
}

// ---------------------------------------------------------------------------
// Knowledge from the Knowledge Curator
// ---------------------------------------------------------------------------

/**
 * The `knowledge/*.json` files of a zip downloaded from the Knowledge Curator. The zip also
 * holds the normalized sources, which the synthesis does not need and ignores.
 */
export function readKnowledgeZip(bytes: Uint8Array): Record<string, string> {
  if (bytes.length > MAX_ZIP_BYTES)
    throw new Error(`The zip is over ${MAX_ZIP_BYTES / 1024 / 1024} MB.`);
  let entries: Record<string, Uint8Array>;
  try {
    entries = unzipSync(bytes);
  } catch {
    throw new Error("This is not a valid .zip file.");
  }
  const knowledge: Record<string, string> = {};
  for (const [path, data] of Object.entries(entries)) {
    const parts = path.split("/");
    const base = parts.pop() as string;
    if (parts.at(-1) === "knowledge" && base.endsWith(".json"))
      knowledge[`knowledge/${base}`] = strFromU8(data);
  }
  if (Object.keys(knowledge).length === 0)
    throw new Error(
      "No knowledge files found. Use the .zip downloaded from the Knowledge Curator.",
    );
  return parseKnowledge(knowledge);
}

// ---------------------------------------------------------------------------
// Sections against the curated knowledge
// ---------------------------------------------------------------------------

/** The section id of a `knowledge/<id>.json` path. */
export const knowledgeId = (path: string) => path.replace(/^knowledge\//, "").replace(/\.json$/, "");

/**
 * Where each section gets its facts: level 0 sections are written from their own curated
 * knowledge, in parallel; a derived section (with `depends_on`) is written from the finished
 * text of its prerequisites, one level after the last of them. Null when a dependency is
 * unknown or the dependencies form a cycle.
 */
export function writingOrder(sections: SectionInput[]): string[][] | null {
  const deps = new Map(sections.map((s) => [s.id, s.depends_on]));
  const level = new Map<string, number>();
  const visiting = new Set<string>();
  const visit = (id: string): number | null => {
    const known = level.get(id);
    if (known !== undefined) return known;
    const d = deps.get(id);
    if (!d || visiting.has(id)) return null;
    visiting.add(id);
    let n = 0;
    for (const dep of d) {
      const l = visit(dep);
      if (l === null) return null;
      n = Math.max(n, l + 1);
    }
    visiting.delete(id);
    level.set(id, n);
    return n;
  };
  for (const s of sections) if (visit(s.id) === null) return null;
  const rows: string[][] = [];
  for (const s of sections) (rows[level.get(s.id)!] ??= []).push(s.id);
  return rows;
}

/**
 * What stops a run, in words for the user, or an empty list when the sections and the
 * knowledge fit together. The synthesizer needs knowledge for exactly the sections that
 * have no `depends_on`.
 */
export function diagnose(
  sections: SectionInput[],
  knowledgeIds: string[],
  maxSections: number,
): string[] {
  const problems: string[] = [];
  if (sections.length === 0) return ["Add at least one section, or load the example."];
  if (sections.length > maxSections) problems.push(`At most ${maxSections} sections.`);
  const ids = sections.map((s) => s.id);
  if (sections.some((s) => !s.title.trim())) problems.push("Every section needs a title.");
  if (ids.some((id) => !/^[A-Za-z0-9_-]+$/.test(id)))
    problems.push("A section id may only hold letters, digits, _ and -.");
  for (const id of new Set(ids.filter((id, i) => ids.indexOf(id) !== i)))
    problems.push(`Two sections have the id "${id}".`);
  let structural = false;
  for (const s of sections) {
    const unknown = s.depends_on.filter((d) => !ids.includes(d));
    if (unknown.length) {
      structural = true;
      problems.push(`"${s.title || s.id}" depends on ${unknown.join(", ")}, which is not a section.`);
    }
    if (s.depends_on.includes(s.id)) {
      structural = true;
      problems.push(`"${s.title || s.id}" cannot depend on itself.`);
    }
  }
  if (!structural && writingOrder(sections) === null)
    problems.push("The dependencies form a cycle: a section cannot wait for itself.");

  const derived = new Set(sections.filter((s) => s.depends_on.length).map((s) => s.id));
  for (const s of sections) {
    if (!derived.has(s.id) && !knowledgeIds.includes(s.id))
      problems.push(
        `No knowledge for "${s.title || s.id}". Curate it in the Knowledge Curator with the id "${s.id}", or make the section depend on other sections.`,
      );
  }
  for (const id of knowledgeIds) {
    if (derived.has(id))
      problems.push(
        `"${id}" depends on other sections, so it is written from their text and cannot use its own knowledge. Remove its dependencies, or curate without this section.`,
      );
    else if (!ids.includes(id))
      problems.push(`The knowledge for "${id}" has no section. Add a section with the id "${id}".`);
  }
  return problems;
}

// ---------------------------------------------------------------------------
// Run request validation (the Next route)
// ---------------------------------------------------------------------------

/** The refusal for a malformed or oversized run request, or null when it is valid. */
export async function checkSynthesizeForm(
  form: FormData,
  limits: Pick<
    ReportWriterLimits,
    "maxUploadMb" | "maxSections" | "maxEvidenceChars" | "maxReviewAttempts"
  >,
): Promise<{ status: 400 | 413; error: string } | null> {
  const raw = form.get("request");
  if (typeof raw !== "string") return { status: 400, error: "Missing request." };
  let request: Partial<SynthRequest> | null;
  try {
    request = JSON.parse(raw);
  } catch {
    return { status: 400, error: "Invalid request JSON." };
  }
  const sections = request?.sections;
  if (!Array.isArray(sections) || sections.length === 0)
    return { status: 400, error: "The request lists no sections." };
  if (sections.length > limits.maxSections)
    return { status: 400, error: `Too many sections (max ${limits.maxSections}).` };
  const attempts = request?.options?.review_attempts;
  if (typeof attempts === "number" && attempts > limits.maxReviewAttempts)
    return {
      status: 400,
      error: `Too many review attempts (max ${limits.maxReviewAttempts}).`,
    };

  const upload = form.get("artifacts");
  if (!(upload instanceof File))
    return { status: 400, error: "artifacts must be a file." };
  let bytes = upload.size;
  let files: Record<string, string>;
  try {
    files = parseKnowledge(JSON.parse(await upload.text()));
  } catch (e) {
    return { status: 400, error: e instanceof Error ? e.message : String(e) };
  }
  if (Object.keys(files).length === 0)
    return {
      status: 400,
      error: "No knowledge files. Curate knowledge in the Knowledge Curator first.",
    };
  const chars = Object.values(files).reduce((n, t) => n + t.length, 0);
  if (chars > limits.maxEvidenceChars)
    return {
      status: 413,
      error: `The knowledge holds ${chars} characters, over the ${limits.maxEvidenceChars} limit.`,
    };

  const sample = form.get("sample_report");
  if (sample !== null) {
    if (!(sample instanceof File))
      return { status: 400, error: "sample_report must be a file." };
    if (!isSampleFile(sample.name))
      return {
        status: 400,
        error: `The sample report must be one of ${SAMPLE_EXTENSIONS.join(", ")}.`,
      };
    if (sample.size > MAX_SAMPLE_BYTES)
      return { status: 413, error: "The sample report is over 1 MB." };
    bytes += sample.size;
  }
  if (bytes > limits.maxUploadMb * 1024 * 1024)
    return { status: 413, error: `Uploads exceed the ${limits.maxUploadMb} MB limit.` };
  return null;
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------

export interface ReviewEdit {
  search: string;
  replace: string;
  reason: string;
}

export interface ReviewEntry {
  section_id: string;
  applied: ReviewEdit[];
  unresolved: ReviewEdit[];
}

export interface ReportSection {
  id: string;
  title: string;
  text: string;
}

export interface SynthResult {
  title: string;
  markdown: string;
  sections: ReportSection[];
  review_log: ReviewEntry[];
  usage: Record<string, number>;
  docx_b64: string | null;
  docx_error: string | null;
}

/** Validate a run result; throws on a malformed one, so the page shows an error. */
export function parseResult(value: unknown): SynthResult {
  const v = value as Partial<SynthResult> | null;
  if (
    !v ||
    typeof v.title !== "string" ||
    typeof v.markdown !== "string" ||
    !Array.isArray(v.sections) ||
    v.sections.some(
      (s) => typeof s?.id !== "string" || typeof s.title !== "string" || typeof s.text !== "string",
    ) ||
    !Array.isArray(v.review_log) ||
    !v.usage ||
    typeof v.usage !== "object"
  )
    throw new Error("The synthesis result is malformed.");
  return {
    title: v.title,
    markdown: v.markdown,
    sections: v.sections,
    review_log: v.review_log,
    usage: v.usage,
    docx_b64: v.docx_b64 ?? null,
    docx_error: v.docx_error ?? null,
  };
}

/** The report as gaik writes it: the title, then each section under its heading. */
export function assemble(title: string, sections: ReportSection[]): string {
  return (
    [`# ${title}`, ...sections.map((s) => `## ${s.title}\n\n${s.text.trim()}`)].join("\n\n") + "\n"
  );
}

export function decodeDocx(b64: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

/** report.md, sections/NN_<id>.md, review_log.json and, if built, report.docx. */
export function zipReport(
  title: string,
  sections: ReportSection[],
  reviewLog: ReviewEntry[],
  docx: Uint8Array | null,
): Uint8Array {
  const entries: Record<string, Uint8Array> = {
    "report.md": strToU8(assemble(title, sections)),
    "review_log.json": strToU8(JSON.stringify(reviewLog, null, 2)),
  };
  sections.forEach((s, i) => {
    const n = String(i + 1).padStart(2, "0");
    entries[`sections/${n}_${s.id}.md`] = strToU8(`## ${s.title}\n\n${s.text.trim()}\n`);
  });
  if (docx) entries["report.docx"] = docx;
  return zipSync(entries);
}
