// Report Writer v2 (CURACT): the spec and text-workspace contract shared by the
// page and its Next route. Pure functions only.
import { strToU8, zipSync } from "fflate";
import type { ReportWriterLimits } from "@/lib/report-writer/limits";

export const STAGES = ["normalize", "curate", "synthesize", "rebuild"] as const;
export type Stage = (typeof STAGES)[number];
export type SourceClass = "primary" | "secondary";

export const MODEL_KEYS = [
  "vision",
  "transcription",
  "curator",
  "writer",
  "reviewer",
] as const;
export type ModelKey = (typeof MODEL_KEYS)[number];

export interface SpecSection {
  id: string;
  title: string;
  instructions: string;
  required_items: string[];
  depends_on: string[];
}

export interface ReportSpec {
  title: string;
  description: string;
  language: string;
  sections: SpecSection[];
  instructions: string;
  sources: Record<SourceClass, string[]>;
  sample_report: string | null;
  models: Record<ModelKey, string | null>;
  settings: RunSettings;
}

export interface StepOptions {
  reasoning_effort: string | null;
  temperature: number | null;
}

export const STEP_KEYS = ["curator", "writer", "reviewer"] as const;
export type StepKey = (typeof STEP_KEYS)[number];

export interface RunSettings extends Record<StepKey, StepOptions> {
  transcription_language: string;
  curator_workers: number;
  review_attempts: number;
  strict_review: boolean;
  docx: boolean;
}

/** The defaults of gaik's RunSettings. */
export const DEFAULT_SETTINGS: RunSettings = {
  transcription_language: "auto",
  curator_workers: 4,
  review_attempts: 5,
  strict_review: false,
  docx: true,
  curator: { reasoning_effort: null, temperature: null },
  writer: { reasoning_effort: null, temperature: null },
  reviewer: { reasoning_effort: null, temperature: null },
};

// ---------------------------------------------------------------------------
// Spec validation (the backend rejects unknown keys, so this does too)
// ---------------------------------------------------------------------------

function fail(msg: string): never {
  throw new Error(`Invalid spec: ${msg}.`);
}

function exactObject(
  v: unknown,
  what: string,
  keys: readonly string[],
): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v))
    fail(`${what} must be an object`);
  const o = v as Record<string, unknown>;
  const missing = keys.filter((k) => !(k in o));
  const extra = Object.keys(o).filter((k) => !keys.includes(k));
  if (missing.length) fail(`${what} is missing ${missing.join(", ")}`);
  if (extra.length) fail(`${what} has unknown keys ${extra.join(", ")}`);
  return o;
}

function str(v: unknown, what: string): string {
  if (typeof v !== "string") fail(`${what} must be a string`);
  return v;
}

function strs(v: unknown, what: string): string[] {
  if (!Array.isArray(v) || v.some((x) => typeof x !== "string"))
    fail(`${what} must be an array of strings`);
  return v;
}

function posInt(v: unknown, what: string): number {
  if (!Number.isInteger(v) || (v as number) < 1)
    fail(`${what} must be an integer of at least 1`);
  return v as number;
}

function bool(v: unknown, what: string): boolean {
  if (typeof v !== "boolean") fail(`${what} must be a boolean`);
  return v;
}

function parseSettings(v: unknown): RunSettings {
  const o = exactObject(v, "settings", Object.keys(DEFAULT_SETTINGS));
  const step = (k: StepKey): StepOptions => {
    const s = exactObject(o[k], `settings.${k}`, [
      "reasoning_effort",
      "temperature",
    ]);
    if (s.temperature !== null && typeof s.temperature !== "number")
      fail(`settings.${k}.temperature must be a number or null`);
    return {
      reasoning_effort:
        s.reasoning_effort === null
          ? null
          : str(s.reasoning_effort, `settings.${k}.reasoning_effort`),
      temperature: s.temperature,
    };
  };
  return {
    transcription_language: str(
      o.transcription_language,
      "settings.transcription_language",
    ),
    curator_workers: posInt(o.curator_workers, "settings.curator_workers"),
    review_attempts: posInt(o.review_attempts, "settings.review_attempts"),
    strict_review: bool(o.strict_review, "settings.strict_review"),
    docx: bool(o.docx, "settings.docx"),
    curator: step("curator"),
    writer: step("writer"),
    reviewer: step("reviewer"),
  };
}

export function parseSpec(value: unknown): ReportSpec {
  const o = exactObject(value, "spec", [
    "title",
    "description",
    "language",
    "sections",
    "instructions",
    "sources",
    "sample_report",
    "models",
    "settings",
  ]);
  if (!Array.isArray(o.sections)) fail("sections must be an array");
  const sections = o.sections.map((s, i) => {
    const w = `sections[${i}]`;
    const r = exactObject(s, w, [
      "id",
      "title",
      "instructions",
      "required_items",
      "depends_on",
    ]);
    return {
      id: str(r.id, `${w}.id`),
      title: str(r.title, `${w}.title`),
      instructions: str(r.instructions, `${w}.instructions`),
      required_items: strs(r.required_items, `${w}.required_items`),
      depends_on: strs(r.depends_on, `${w}.depends_on`),
    };
  });
  const src = exactObject(o.sources, "sources", ["primary", "secondary"]);
  const m = exactObject(o.models, "models", MODEL_KEYS);
  const models = Object.fromEntries(
    MODEL_KEYS.map((k) => [
      k,
      m[k] === null ? null : str(m[k], `models.${k}`),
    ]),
  ) as Record<ModelKey, string | null>;
  return {
    title: str(o.title, "title"),
    description: str(o.description, "description"),
    language: str(o.language, "language"),
    sections,
    instructions: str(o.instructions, "instructions"),
    sources: {
      primary: strs(src.primary, "sources.primary"),
      secondary: strs(src.secondary, "sources.secondary"),
    },
    sample_report:
      o.sample_report === null ? null : str(o.sample_report, "sample_report"),
    models,
    settings: parseSettings(o.settings),
  };
}

// ---------------------------------------------------------------------------
// Artifact paths
// ---------------------------------------------------------------------------

export const ARTIFACT_PATH =
  /^(normalized\/[\w.-]+\.(md|json)|knowledge\/[\w.-]+\.json|report\/sections\/[\w.-]+\.md|report\/review_log\.json|report\/report\.md|sample_report\.md)$/;

export const DOCX_PATH = "report/report.docx";

export type ArtifactKind =
  | "normalized"
  | "sample"
  | "knowledge"
  | "section"
  | "review_log"
  | "report";

export function classifyArtifact(path: string): {
  kind: ArtifactKind;
  editable: boolean;
} {
  if (!ARTIFACT_PATH.test(path))
    throw new Error(`Unknown artifact path "${path}".`);
  const kind: ArtifactKind = path.startsWith("normalized/")
    ? "normalized"
    : path === "sample_report.md"
      ? "sample"
      : path.startsWith("knowledge/")
        ? "knowledge"
        : path.startsWith("report/sections/")
          ? "section"
          : path === "report/review_log.json"
            ? "review_log"
            : "report";
  return { kind, editable: kind === "knowledge" || kind === "section" };
}

/** Validate a path-to-text map; throws on an unknown path or non-text value. */
export function parseArtifacts(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Artifacts must be an object mapping path to text.");
  for (const [path, text] of Object.entries(value)) {
    classifyArtifact(path);
    if (typeof text !== "string")
      throw new Error(`Artifact "${path}" must be text.`);
  }
  return value as Record<string, string>;
}

const FOLDERS = ["normalized", "knowledge", "report", ""];

/** Group paths by top-level folder ("" holds sample_report.md), in stage order. */
export function groupArtifacts(
  paths: string[],
): { folder: string; paths: string[] }[] {
  const folderOf = (p: string) => (p.includes("/") ? p.split("/")[0] : "");
  return FOLDERS.map((folder) => ({
    folder,
    paths: paths.filter((p) => folderOf(p) === folder).sort(),
  })).filter((g) => g.paths.length > 0);
}

/** Whether a stage after normalize has the workspace inputs it needs. */
export function stageReady(
  stage: Exclude<Stage, "normalize">,
  artifacts: Record<string, string>,
  hasSample: boolean,
): boolean {
  const has = (prefix: string) =>
    Object.keys(artifacts).some((p) => p.startsWith(prefix));
  if (stage === "curate") return has("normalized/");
  if (stage === "synthesize")
    return has("knowledge/") && (!hasSample || "sample_report.md" in artifacts);
  return has("report/sections/");
}

/** The parse error for a knowledge edit, or null when it is valid JSON. */
export function knowledgeJsonError(text: string): string | null {
  try {
    JSON.parse(text);
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}

// ---------------------------------------------------------------------------
// Staleness
// ---------------------------------------------------------------------------

export interface Staleness {
  knowledge: boolean; // normalized/ changed after curate
  report: boolean; // knowledge/ changed after synthesize
  assembled: boolean; // a section changed after report.md/docx were built
  editedSections: boolean; // synthesize would overwrite hand edits
}

export const FRESH: Staleness = {
  knowledge: false,
  report: false,
  assembled: false,
  editedSections: false,
};

export function staleAfterEdit(s: Staleness, path: string): Staleness {
  const { kind } = classifyArtifact(path);
  if (kind === "knowledge") return { ...s, report: true };
  if (kind === "section")
    return { ...s, assembled: true, editedSections: true };
  throw new Error(`${path} is not editable.`);
}

export function staleAfterStage(s: Staleness, stage: Stage): Staleness {
  switch (stage) {
    case "normalize":
      return { ...s, knowledge: true, report: true };
    case "curate":
      return { ...s, knowledge: false, report: true };
    case "synthesize":
      return { ...FRESH, knowledge: s.knowledge };
    case "rebuild":
      return { ...s, assembled: false };
  }
}

/** The action that refreshes a stale file, or null when it is current. */
export function staleHint(s: Staleness, path: string): string | null {
  if (path.startsWith("knowledge/")) return s.knowledge ? "Rerun Stage 2" : null;
  if (!path.startsWith("report/")) return null;
  if (s.report) return "Rerun Stage 3";
  const assembled = path === "report/report.md" || path === DOCX_PATH;
  return s.assembled && assembled ? "Rebuild report" : null;
}

// ---------------------------------------------------------------------------
// Run request validation (the Next route)
// ---------------------------------------------------------------------------

function parseField<T>(
  raw: FormDataEntryValue | null,
  name: string,
  parse: (v: unknown) => T,
): T {
  if (typeof raw !== "string") throw new Error(`Missing ${name}.`);
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(`Invalid ${name} JSON.`);
  }
  return parse(value);
}

/** The refusal for a malformed or oversized run request, or null when valid. */
export function checkRunForm(
  form: FormData,
  limits: Pick<
    ReportWriterLimits,
    | "maxUploadMb"
    | "maxSections"
    | "maxEvidenceChars"
    | "maxCuratorWorkers"
    | "maxReviewAttempts"
  >,
): { status: 400 | 413; error: string } | null {
  let stage: Stage;
  let spec: ReportSpec;
  let artifacts: Record<string, string>;
  try {
    stage = form.get("stage") as Stage;
    if (!STAGES.includes(stage)) throw new Error(`Invalid stage "${stage}".`);
    spec = parseField(form.get("spec"), "spec", parseSpec);
    artifacts = parseField(form.get("artifacts"), "artifacts", parseArtifacts);
  } catch (e) {
    return { status: 400, error: e instanceof Error ? e.message : String(e) };
  }
  if (spec.sections.length > limits.maxSections)
    return {
      status: 400,
      error: `Too many sections (max ${limits.maxSections}).`,
    };
  if (spec.settings.curator_workers > limits.maxCuratorWorkers)
    return {
      status: 400,
      error: `Too many parallel sections (max ${limits.maxCuratorWorkers}).`,
    };
  if (spec.settings.review_attempts > limits.maxReviewAttempts)
    return {
      status: 400,
      error: `Too many review attempts (max ${limits.maxReviewAttempts}).`,
    };

  const uploads = [...form.getAll("files"), ...form.getAll("sample_report")];
  if (uploads.some((f) => !(f instanceof File)))
    return { status: 400, error: "files and sample_report must be files." };
  const files = uploads as File[];
  if (stage !== "normalize" && files.length)
    return { status: 400, error: "Only the normalize stage accepts files." };
  if (stage === "normalize") {
    // The backend pairs uploads with the spec's names by position.
    const expected = spec.sources.primary.length + spec.sources.secondary.length;
    const got = form.getAll("files").length;
    if (got !== expected)
      return {
        status: 400,
        error: `Upload one file per spec source, in spec order: expected ${expected}, got ${got}.`,
      };
    if (form.has("sample_report") !== (spec.sample_report !== null))
      return {
        status: 400,
        error: "Upload a sample_report exactly when the spec names one.",
      };
  }

  const bytes =
    files.reduce((n, f) => n + f.size, 0) +
    new TextEncoder().encode(form.get("artifacts") as string).length;
  if (bytes > limits.maxUploadMb * 1024 * 1024)
    return {
      status: 413,
      error: `Uploads exceed the ${limits.maxUploadMb} MB limit.`,
    };

  if (stage === "curate") {
    const chars = Object.entries(artifacts)
      .filter(([p]) => p.startsWith("normalized/") && p.endsWith(".md"))
      .reduce((n, [, text]) => n + text.length, 0);
    if (chars > limits.maxEvidenceChars)
      return {
        status: 413,
        error: `The normalized sources hold ${chars} characters, over the ${limits.maxEvidenceChars} limit.`,
      };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Zip
// ---------------------------------------------------------------------------

/** Zip every text artifact at its workspace path, plus report.docx if built. */
export function zipWorkspace(
  artifacts: Record<string, string>,
  docx: Uint8Array | null,
): Uint8Array {
  const entries: Record<string, Uint8Array> = {};
  for (const [path, text] of Object.entries(artifacts))
    entries[path] = strToU8(text);
  if (docx) entries[DOCX_PATH] = docx;
  return zipSync(entries);
}
