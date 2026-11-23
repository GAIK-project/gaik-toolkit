// What kind of file a name or a media type stands for, so a list of files can
// show each one's own mark (components/file-icon). The kinds are the ones the
// wizard meets: the blueprint and the schema (JSON), source material (PDF,
// Word, Excel, CSV, text, recordings, images) and the package's own files
// (Markdown, Python, ZIP).

export const FILE_KINDS = [
  "json",
  "pdf",
  "word",
  "excel",
  "csv",
  "markdown",
  "python",
  "zip",
  "text",
  "audio",
  "image",
] as const;

export type FileKind = (typeof FILE_KINDS)[number];

const BY_EXTENSION: Record<string, FileKind> = {
  json: "json",
  jsonl: "json",
  pdf: "pdf",
  doc: "word",
  docx: "word",
  dotx: "word",
  rtf: "word",
  odt: "word",
  xls: "excel",
  xlsx: "excel",
  xlsm: "excel",
  ods: "excel",
  csv: "csv",
  tsv: "csv",
  md: "markdown",
  mdx: "markdown",
  markdown: "markdown",
  py: "python",
  ipynb: "python",
  zip: "zip",
  gz: "zip",
  tar: "zip",
  tgz: "zip",
  "7z": "zip",
  txt: "text",
  log: "text",
  mp3: "audio",
  wav: "audio",
  m4a: "audio",
  ogg: "audio",
  flac: "audio",
  aac: "audio",
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  webp: "image",
  tif: "image",
  tiff: "image",
  bmp: "image",
  svg: "image",
};

const BY_MEDIA_TYPE: Record<string, FileKind> = {
  "application/json": "json",
  "application/x-ndjson": "json",
  "application/pdf": "pdf",
  "application/msword": "word",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
  "application/rtf": "word",
  "application/vnd.oasis.opendocument.text": "word",
  "application/vnd.ms-excel": "excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
  "application/vnd.oasis.opendocument.spreadsheet": "excel",
  "text/csv": "csv",
  "text/tab-separated-values": "csv",
  "text/markdown": "markdown",
  "text/x-python": "python",
  "application/x-python-code": "python",
  "application/zip": "zip",
  "application/x-zip-compressed": "zip",
  "application/gzip": "zip",
  "application/x-tar": "zip",
  "application/x-7z-compressed": "zip",
  "text/plain": "text",
};

/**
 * The kind of a file, from its name ("report.final.PDF", a path) or its media
 * type ("application/pdf; charset=binary"). Null for a kind without a mark of
 * its own: the caller then shows the plain file icon.
 */
export function fileKind(nameOrType: string | null | undefined): FileKind | null {
  const text = (nameOrType ?? "").trim().toLowerCase();
  if (!text) return null;

  const type = text.split(";")[0].trim();
  if (Object.prototype.hasOwnProperty.call(BY_MEDIA_TYPE, type)) return BY_MEDIA_TYPE[type];

  // A path such as "text/plan.json" also looks like a media type, so a known
  // extension is read before a media type's family.
  const base = text.split(/[\\/]/).pop() ?? "";
  const dot = base.lastIndexOf(".");
  // ".env" is a name, not an extension.
  const ext = dot > 0 ? base.slice(dot + 1) : "";
  if (ext && Object.prototype.hasOwnProperty.call(BY_EXTENSION, ext)) return BY_EXTENSION[ext];

  if (/^[a-z0-9.+-]+\/[a-z0-9.+-]+$/.test(type)) {
    if (type.startsWith("audio/")) return "audio";
    if (type.startsWith("image/")) return "image";
    if (type.endsWith("+json")) return "json";
    if (type.startsWith("text/")) return "text";
  }
  return null;
}

// A file name inside a sentence: a word with one of the known extensions,
// with or without a path in front of it.
const NAMED_FILE = new RegExp(
  `[\\w./\\\\-]*[\\w-]\\.(?:${Object.keys(BY_EXTENSION).join("|")})(?![\\w-])`,
  "i",
);

/**
 * The kind of the first file a line of text names ("Kirjoitetaan
 * output_schema.json" → "json"); null when it names none.
 */
export function fileKindInText(text: string): FileKind | null {
  const match = NAMED_FILE.exec(text);
  return match ? fileKind(match[0]) : null;
}
