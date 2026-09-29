// Source Normalizer demo: the request and result contract shared by the page and
// its Next route. Pure functions only.
import { strToU8, zipSync } from "fflate";
import type { ReportWriterLimits } from "@/lib/report-writer/limits";

export const MAX_FILES = 20;

export type SourceClass = "primary" | "secondary";

/** The file types gaik's SourceNormalizer converts, by kind. */
export const FILE_KINDS = [
  { kind: "Documents", note: "PDF with a text layer (no scans), Word", extensions: [".pdf", ".docx"] },
  { kind: "Spreadsheets", note: "one table per sheet", extensions: [".xlsx", ".csv"] },
  { kind: "Text", note: "read as UTF-8", extensions: [".txt", ".md"] },
  {
    kind: "Recordings",
    note: "transcribed",
    extensions: [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mpeg", ".mpga"],
  },
  { kind: "Images", note: "described by a vision model", extensions: [".png", ".jpg", ".jpeg", ".webp"] },
] as const;

const SUPPORTED = new Set<string>(FILE_KINDS.flatMap((k) => k.extensions));

/** The `accept` value of the file picker. */
export const ACCEPT = [...SUPPORTED].join(",");

/** Types people commonly try that the normalizer refuses. */
export const UNSUPPORTED_HINT =
  "Not supported: PowerPoint (.pptx), old Office formats (.doc, .xls), scanned PDFs without a text layer.";

/** Whether a file name has an extension the normalizer converts. */
export function isSupportedFile(name: string): boolean {
  const dot = name.lastIndexOf(".");
  return dot >= 0 && SUPPORTED.has(name.slice(dot).toLowerCase());
}

export interface NormalizeOptions {
  transcription_model: string | null;
  vision_model: string | null;
  language: string;
}

export const DEFAULT_OPTIONS: NormalizeOptions = {
  transcription_model: null,
  vision_model: null,
  language: "auto",
};

export interface ManifestSource {
  name: string;
  source_class: SourceClass;
}

export interface Manifest {
  sources: ManifestSource[];
  options: NormalizeOptions;
}

/** One entry of `normalized/sources.json`, as gaik's NormalizedSources.save writes it. */
export interface NormalizedEntry {
  id: string;
  file: string;
  source_class: SourceClass | null;
  source_type: string;
  tool: string;
}

export const MANIFEST_PATH = "normalized/sources.json";
const ARTIFACT_PATH = /^normalized\/([\w.-]+\.md|sources\.json)$/;

/** The manifest for `rows`, in row order: the backend pairs uploads by position. */
export function buildManifest(
  rows: { name: string; sourceClass: SourceClass }[],
  options: NormalizeOptions,
): Manifest {
  const clean = (v: string | null) => (v?.trim() ? v.trim() : null);
  return {
    sources: rows.map((r) => ({ name: r.name, source_class: r.sourceClass })),
    options: {
      transcription_model: clean(options.transcription_model),
      vision_model: clean(options.vision_model),
      language: options.language.trim() || "auto",
    },
  };
}

/** The refusal for a malformed or oversized request, or null when it is valid. */
export function checkNormalizeForm(
  form: FormData,
  limits: Pick<ReportWriterLimits, "maxUploadMb">,
): { status: 400 | 413; error: string } | null {
  const raw = form.get("manifest");
  if (typeof raw !== "string") return { status: 400, error: "Missing manifest." };
  let manifest: unknown;
  try {
    manifest = JSON.parse(raw);
  } catch {
    return { status: 400, error: "Invalid manifest JSON." };
  }
  const sources = (manifest as Partial<Manifest> | null)?.sources;
  if (!Array.isArray(sources) || sources.length === 0)
    return { status: 400, error: "The manifest lists no sources." };
  if (sources.length > MAX_FILES)
    return { status: 400, error: `Too many files (max ${MAX_FILES}).` };

  const uploads = form.getAll("files");
  if (uploads.some((f) => !(f instanceof File)))
    return { status: 400, error: "files must be files." };
  if (uploads.length !== sources.length)
    return {
      status: 400,
      error: `Upload one file per manifest source, in order: expected ${sources.length}, got ${uploads.length}.`,
    };
  const bytes = (uploads as File[]).reduce((n, f) => n + f.size, 0);
  if (bytes > limits.maxUploadMb * 1024 * 1024)
    return {
      status: 413,
      error: `Uploads exceed the ${limits.maxUploadMb} MB limit.`,
    };
  return null;
}

/** Validate a result's path-to-text map; throws on an unknown path or non-text value. */
export function parseArtifacts(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Artifacts must be an object mapping path to text.");
  for (const [path, text] of Object.entries(value)) {
    if (!ARTIFACT_PATH.test(path))
      throw new Error(`Unknown artifact path "${path}".`);
    if (typeof text !== "string")
      throw new Error(`Artifact "${path}" must be text.`);
  }
  if (!(MANIFEST_PATH in value))
    throw new Error(`The result has no ${MANIFEST_PATH}.`);
  return value as Record<string, string>;
}

/** The per-file metadata of a result, in file order. */
export function readManifest(artifacts: Record<string, string>): NormalizedEntry[] {
  const entries: unknown = JSON.parse(artifacts[MANIFEST_PATH] ?? "[]");
  if (!Array.isArray(entries))
    throw new Error(`${MANIFEST_PATH} must be a list.`);
  return entries as NormalizedEntry[];
}

/** Zip every artifact at its path: a folder `NormalizedSources.load` reads back. */
export function zipArtifacts(artifacts: Record<string, string>): Uint8Array {
  const entries: Record<string, Uint8Array> = {};
  for (const [path, text] of Object.entries(artifacts))
    entries[path] = strToU8(text);
  return zipSync(entries);
}
