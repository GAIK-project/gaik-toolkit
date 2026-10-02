// What the Source Normalizer demo works with: how each kind of file is converted,
// ready-made source sets, and how the converted texts are searched and described.

import type { SourceClass } from "@/lib/source-normalizer/workspace";

export interface KindInfo {
  label: string;
  /** What turns the file into text. */
  tool: string;
  /** What the text of it is like. */
  text: string;
  /** Whether a model is called: slower, and counted in the usage. */
  usesModel: boolean;
}

const AUDIO = [
  ".mp3",
  ".wav",
  ".m4a",
  ".ogg",
  ".flac",
  ".webm",
  ".mp4",
  ".mpeg",
  ".mpga",
];
const IMAGES = [".png", ".jpg", ".jpeg", ".webp"];

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

/** How a file is converted, from its name. */
export function kindOf(name: string): KindInfo {
  const extension = extensionOf(name);
  if (extension === ".pdf")
    return {
      label: "PDF",
      tool: "PyMuPDFParser",
      text: "The text layer, with a [Page N] line before each page.",
      usesModel: false,
    };
  if (extension === ".docx")
    return {
      label: "Word",
      tool: "DocxParser",
      text: "Headings as # headings, with paragraphs and tables in document order.",
      usesModel: false,
    };
  if (extension === ".xlsx" || extension === ".csv")
    return {
      label: "Spreadsheet",
      tool: "SpreadsheetParser",
      text: "A Markdown table for each sheet, with a Row column of source row numbers.",
      usesModel: false,
    };
  if (extension === ".txt" || extension === ".md")
    return {
      label: "Text",
      tool: "text",
      text: "The file as it is, read as UTF-8.",
      usesModel: false,
    };
  if (AUDIO.includes(extension))
    return {
      label: "Recording",
      tool: "Transcriber",
      text: "The raw transcript. It has no timestamps for each utterance.",
      usesModel: true,
    };
  if (IMAGES.includes(extension))
    return {
      label: "Image",
      tool: "VisionParser",
      text: "A description in Markdown, written by a vision model.",
      usesModel: true,
    };
  return { label: "Unknown", tool: "–", text: "", usesModel: false };
}

export const hasRecordings = (names: string[]): boolean =>
  names.some((name) => AUDIO.includes(extensionOf(name)));
export const hasImages = (names: string[]): boolean =>
  names.some((name) => IMAGES.includes(extensionOf(name)));

export interface SourceExample {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  /** Files in a folder of public/, or fetched from the Report Writer example. */
  files: { url: string; name: string; sourceClass: SourceClass }[];
}

const DIR = "/source-normalizer-examples";

export const EXAMPLES: SourceExample[] = [
  {
    id: "package",
    title: "A site meeting package",
    summary:
      "Meeting minutes, a visit note and a maintenance log. Everything is converted locally: no model is called, so it is quick.",
    tags: ["PDF", "text", "spreadsheet", "no model calls"],
    files: [
      {
        url: "/extractor-examples/meeting-minutes.pdf",
        name: "meeting-minutes.pdf",
        sourceClass: "primary",
      },
      {
        url: `${DIR}/site-notes.txt`,
        name: "site-notes.txt",
        sourceClass: "primary",
      },
      {
        url: `${DIR}/maintenance-log.csv`,
        name: "maintenance-log.csv",
        sourceClass: "secondary",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Reading the texts
// ---------------------------------------------------------------------------

export interface Described {
  chars: number;
  words: number;
  lines: number;
}

export function describeText(text: string): Described {
  const trimmed = text.trim();
  return {
    chars: text.length,
    words: trimmed === "" ? 0 : trimmed.split(/\s+/).length,
    lines: trimmed === "" ? 0 : trimmed.split(/\r?\n/).length,
  };
}

/** How many sources of each class a run holds. */
export function countByClass(
  entries: { source_class: SourceClass | null }[],
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const entry of entries) {
    const key = entry.source_class ?? "unlabelled";
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

/** The number of progress messages that tell a file is done, as a part of 0 to 1. */
export function progressShare(messages: number, files: number): number {
  if (files <= 0) return 0;
  return Math.max(0, Math.min(1, messages / files));
}
