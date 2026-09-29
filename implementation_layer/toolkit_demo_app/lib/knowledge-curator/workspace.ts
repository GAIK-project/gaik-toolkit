// Knowledge Curator demo: the request and result contract shared by the page and its
// Next route. Pure functions only.
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import type { ReportWriterLimits } from "@/lib/report-writer/limits";
import {
  MANIFEST_PATH,
  parseArtifacts as parseNormalized,
} from "@/lib/source-normalizer/workspace";

export const MAX_ZIP_BYTES = 20 * 1024 * 1024;

export const EFFORTS = ["minimal", "low", "medium", "high"] as const;
export type Effort = (typeof EFFORTS)[number];

export interface SectionInput {
  id: string;
  title: string;
  instructions: string;
  required_items: string[];
}

export interface CuratorOptions {
  model: string | null;
  reasoning_effort: Effort | null;
  max_workers: number;
}

export const DEFAULT_OPTIONS: CuratorOptions = {
  model: null,
  reasoning_effort: null,
  max_workers: 4,
};

export interface CurateRequest {
  sections: SectionInput[];
  instructions: string;
  options: CuratorOptions;
}

export interface DroppedUnit {
  section_id: string;
  topic: string;
  summary: string;
  quote: string;
  file: string;
  reason: string;
}

export interface QuoteFailure {
  section_id: string;
  unit_id: string;
  file: string;
  quote: string;
  reason: string;
}

export interface VerifyResult {
  units: number;
  failures: QuoteFailure[];
}

export interface FactUnit {
  id: string;
  topic: string;
  time_qualifier: string | null;
  summary: string;
  quote: string;
  source: { file: string; locator: string | null };
  source_class: string | null;
  confidence: string;
}

export interface SectionKnowledge {
  section_id: string;
  units: FactUnit[];
  missing: string[];
  conflicts: {
    topic: string;
    description: string;
    status: string;
    unit_ids: string[];
  }[];
}

const KNOWLEDGE_PATH = /^knowledge\/[\w.-]+\.json$/;

export const knowledgePath = (sectionId: string) => `knowledge/${sectionId}.json`;

export function buildRequest(
  sections: SectionInput[],
  instructions: string,
  options: CuratorOptions,
): CurateRequest {
  const clean = (v: string | null) => (v?.trim() ? v.trim() : null);
  return {
    sections: sections.map((s) => ({
      id: s.id,
      title: s.title.trim(),
      instructions: s.instructions.trim(),
      required_items: s.required_items.map((x) => x.trim()).filter(Boolean),
    })),
    instructions: instructions.trim(),
    options: { ...options, model: clean(options.model) },
  };
}

/** The first problem with the sections before a run, or null when they are valid. */
export function sectionsProblem(
  sections: SectionInput[],
  maxSections: number,
): string | null {
  if (sections.length === 0) return "Add at least one topic.";
  if (sections.length > maxSections)
    return `At most ${maxSections} topics.`;
  if (sections.some((s) => !s.title.trim())) return "Every topic needs a title.";
  const ids = sections.map((s) => s.id);
  if (ids.some((id) => !/^[A-Za-z0-9_-]+$/.test(id)))
    return "A topic id may only hold letters, digits, _ and -.";
  const dup = ids.find((id, i) => ids.indexOf(id) !== i);
  return dup ? `Two topics have the id "${dup}".` : null;
}

/** The refusal for a malformed or oversized run request, or null when it is valid. */
export async function checkCurateForm(
  form: FormData,
  limits: Pick<
    ReportWriterLimits,
    "maxUploadMb" | "maxSections" | "maxEvidenceChars" | "maxCuratorWorkers"
  >,
): Promise<{ status: 400 | 413; error: string } | null> {
  const raw = form.get("request");
  if (typeof raw !== "string") return { status: 400, error: "Missing request." };
  let request: Partial<CurateRequest> | null;
  try {
    request = JSON.parse(raw);
  } catch {
    return { status: 400, error: "Invalid request JSON." };
  }
  const sections = request?.sections;
  if (!Array.isArray(sections) || sections.length === 0)
    return { status: 400, error: "The request lists no topics." };
  if (sections.length > limits.maxSections)
    return { status: 400, error: `Too many topics (max ${limits.maxSections}).` };
  const workers = request?.options?.max_workers;
  if (typeof workers === "number" && workers > limits.maxCuratorWorkers)
    return {
      status: 400,
      error: `Too many parallel topics (max ${limits.maxCuratorWorkers}).`,
    };

  const upload = form.get("artifacts");
  if (!(upload instanceof File))
    return { status: 400, error: "artifacts must be a file." };
  if (upload.size > limits.maxUploadMb * 1024 * 1024)
    return { status: 413, error: `Uploads exceed the ${limits.maxUploadMb} MB limit.` };
  let files: Record<string, string>;
  try {
    files = parseNormalized(JSON.parse(await upload.text()));
  } catch (e) {
    return { status: 400, error: e instanceof Error ? e.message : String(e) };
  }
  const chars = Object.entries(files)
    .filter(([p]) => p.endsWith(".md"))
    .reduce((n, [, text]) => n + text.length, 0);
  if (chars > limits.maxEvidenceChars)
    return {
      status: 413,
      error: `The normalized sources hold ${chars} characters, over the ${limits.maxEvidenceChars} limit.`,
    };
  return null;
}

/** Validate a knowledge path-to-text map; throws on an unknown path or non-text value. */
export function parseKnowledge(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Artifacts must be an object mapping path to text.");
  for (const [path, text] of Object.entries(value)) {
    if (!KNOWLEDGE_PATH.test(path))
      throw new Error(`Unknown artifact path "${path}".`);
    if (typeof text !== "string")
      throw new Error(`Artifact "${path}" must be text.`);
  }
  return value as Record<string, string>;
}

/** A knowledge file as an object, or the reason it cannot be read. */
export function readKnowledge(
  text: string,
): { ok: true; value: SectionKnowledge } | { ok: false; error: string } {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
  const o = value as Partial<SectionKnowledge> | null;
  if (
    !o ||
    typeof o.section_id !== "string" ||
    !Array.isArray(o.units) ||
    !Array.isArray(o.missing) ||
    !Array.isArray(o.conflicts)
  )
    return {
      ok: false,
      error: "Expected section_id, units, missing and conflicts.",
    };
  return { ok: true, value: o as SectionKnowledge };
}

/**
 * The files of a zip made by the Source Normalizer (`normalized/...` or the same files
 * at the top level) or by this demo (which also holds `knowledge/...`).
 */
export function readWorkspaceZip(bytes: Uint8Array): {
  normalized: Record<string, string>;
  knowledge: Record<string, string>;
} {
  if (bytes.length > MAX_ZIP_BYTES)
    throw new Error(`The zip is over ${MAX_ZIP_BYTES / 1024 / 1024} MB.`);
  let entries: Record<string, Uint8Array>;
  try {
    entries = unzipSync(bytes);
  } catch {
    throw new Error("This is not a valid .zip file.");
  }
  const normalized: Record<string, string> = {};
  const knowledge: Record<string, string> = {};
  for (const [path, data] of Object.entries(entries)) {
    if (path.endsWith("/")) continue;
    const parts = path.split("/");
    const base = parts.pop() as string;
    const dir = parts.at(-1) ?? "";
    if (dir === "knowledge" && base.endsWith(".json"))
      knowledge[`knowledge/${base}`] = strFromU8(data);
    else if (
      (dir === "" || dir === "normalized") &&
      (base === "sources.json" || base.endsWith(".md"))
    )
      normalized[`normalized/${base}`] = strFromU8(data);
  }
  if (!(MANIFEST_PATH in normalized))
    throw new Error(
      "No sources.json found. Use the .zip downloaded from the Source Normalizer.",
    );
  return { normalized: parseNormalized(normalized), knowledge: parseKnowledge(knowledge) };
}

/** Zip the normalized sources and the knowledge files at their paths. */
export function zipWorkspace(
  normalized: Record<string, string>,
  knowledge: Record<string, string>,
): Uint8Array {
  const entries: Record<string, Uint8Array> = {};
  for (const files of [normalized, knowledge])
    for (const [path, text] of Object.entries(files)) entries[path] = strToU8(text);
  return zipSync(entries);
}
