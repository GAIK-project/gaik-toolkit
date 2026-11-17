/**
 * One file of the PoC package as the PoC tab's editor sees it.
 *
 * wizard_api decides what may be read and saved (`GET`/`PUT
 * /sessions/{id}/poc/file`); the rules are repeated here for the mock store
 * and so that the tree does not offer what the api will refuse.
 */

export const POC_EDITABLE_SUFFIXES = [
  ".py",
  ".md",
  ".txt",
  ".yaml",
  ".yml",
  ".json",
  ".toml",
  ".cfg",
  ".ini",
  ".html",
  ".css",
  ".js",
] as const;

export const ENV_EXAMPLE_NAME = ".env.example";
export const AI_MARKER_NAME = "AI-GENERATED.json";
export const MAX_POC_FILE_BYTES = 256 * 1024;
const READ_ONLY_DIRS = ["sample_input", "output"];
// The package's own test page: app.py at the root serves ui/. Both are the
// scaffolder's templates; no run reads ui/, so it is outside the digest.
const TEST_PAGE_ENTRY = "app.py";
const TEST_PAGE_DIR = "ui";
const isTestPage = (parts: string[]) =>
  (parts.length === 1 && parts[0] === TEST_PAGE_ENTRY) || (parts.length > 1 && parts[0] === TEST_PAGE_DIR);

/** wizard_api's answer for one file, in the web app's own spelling. */
export type PocFile = {
  /** Relative to `poc/`. */
  path: string;
  content: string;
  /** What a save names as the version it changed. */
  digest: string;
  editable: boolean;
  readOnlyReason: string | null;
  /** A change to this file changes the package a test run is tied to. */
  affectsPackage: boolean;
};

export type PocFileSaved = {
  path: string;
  digest: string;
  affectsPackage: boolean;
  /** The gate the save reopened ("gate_3"), or null. */
  gateReopened: string | null;
};

const text = (v: unknown): string | null => (typeof v === "string" ? v : null);

export function pocFileFrom(raw: unknown): PocFile | null {
  if (typeof raw !== "object" || raw === null) return null;
  const d = raw as Record<string, unknown>;
  const path = text(d.path);
  const content = text(d.content);
  const digest = text(d.digest);
  if (path === null || content === null || digest === null) return null;
  return {
    path,
    content,
    digest,
    editable: d.editable === true,
    readOnlyReason: text(d.read_only_reason),
    affectsPackage: d.affects_package === true,
  };
}

export function pocFileSavedFrom(raw: unknown): PocFileSaved | null {
  if (typeof raw !== "object" || raw === null) return null;
  const d = raw as Record<string, unknown>;
  const path = text(d.path);
  const digest = text(d.digest);
  if (path === null || digest === null) return null;
  return {
    path,
    digest,
    affectsPackage: d.affects_package === true,
    gateReopened: text(d.gate_reopened),
  };
}

/**
 * A name in the deployment package's tree (`poc/run_poc.py`) as the path the
 * editor asks for (`run_poc.py`); null for what lies beside `poc/` (the
 * blueprint, the diagrams, the documentation), which the editor does not open.
 */
export function pocPathOf(packagePath: string): string | null {
  return packagePath.startsWith("poc/") && packagePath.length > 4 ? packagePath.slice(4) : null;
}

/** `.env`, every `.env*` name but `.env.example`, and every `*.env`: a file that would hold keys. */
export function isSecretEnvName(path: string): boolean {
  const name = (path.split(/[\\/]/).pop() ?? "").toLowerCase();
  if (name === ENV_EXAMPLE_NAME) return false;
  return name.startsWith(".env") || name.endsWith(".env");
}

const outsideDigest = (folder: string) => folder.startsWith(".") || folder === "__pycache__";

/**
 * Why the editor may not save `path` (relative to `poc/`), as wizard_api's code; null when it may.
 * Nor in a hidden folder or `__pycache__`: those are outside the package digest. Nor the test
 * page (`app.py` at the root, everything under `ui/`). Whether code may be saved at all depends
 * on the deployment's runner key, which only wizard_api knows: its answer says so.
 */
export function pocFileReadOnly(path: string): "file_read_only" | "file_type_not_editable" | null {
  const parts = path.split("/");
  const name = parts[parts.length - 1];
  if (name === AI_MARKER_NAME || READ_ONLY_DIRS.includes(parts[0])) return "file_read_only";
  if (parts.slice(0, -1).some(outsideDigest) || isTestPage(parts)) return "file_read_only";
  if (name !== ENV_EXAMPLE_NAME && !POC_EDITABLE_SUFFIXES.some((s) => name.toLowerCase().endsWith(s))) {
    return "file_type_not_editable";
  }
  return null;
}

/**
 * Whether saving `path` changes the package a test run is tied to, as wizard_api
 * says it (`poc_service.counts_for_package_digest`), for the mock store: every
 * file the editor saves but a README outside `prompts/`.
 */
export function pocFileAffectsPackage(path: string): boolean {
  const parts = path.split("/");
  const name = parts[parts.length - 1];
  if (READ_ONLY_DIRS.includes(parts[0]) || parts.slice(0, -1).some(outsideDigest)) return false;
  if (parts.length > 1 && parts[0] === TEST_PAGE_DIR) return false;
  if (name === AI_MARKER_NAME || isSecretEnvName(name)) return false;
  return !(name.toLowerCase() === "readme.md" && parts[0] !== "prompts");
}

export type EditorLanguage =
  | "python"
  | "json"
  | "yaml"
  | "markdown"
  | "html"
  | "css"
  | "javascript"
  | "toml"
  | "properties";

const LANGUAGE_BY_SUFFIX: Record<string, EditorLanguage> = {
  py: "python",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  md: "markdown",
  html: "html",
  css: "css",
  js: "javascript",
  toml: "toml",
  cfg: "properties",
  ini: "properties",
};

/** The highlighting a file gets from its name; null for plain text. */
export function editorLanguage(path: string): EditorLanguage | null {
  const name = (path.split("/").pop() ?? "").toLowerCase();
  if (name === ENV_EXAMPLE_NAME) return "properties";
  const dot = name.lastIndexOf(".");
  return dot > 0 ? (LANGUAGE_BY_SUFFIX[name.slice(dot + 1)] ?? null) : null;
}

/** The size of `content` as the api counts it: UTF-8 bytes. */
export function utf8Bytes(content: string): number {
  return new TextEncoder().encode(content).length;
}
