// What the Transcriber demo works with: the options and what each does, ready-made
// recordings with the options that suit them, and how a transcript is read.

export type Language = "auto" | "fi" | "en";

export const LANGUAGES: { id: Language; label: string; hint: string }[] = [
  {
    id: "auto",
    label: "Auto-detect",
    hint: "Recognised from the speech. A good choice when it varies or is not known.",
  },
  {
    id: "fi",
    label: "Finnish",
    hint: "OpenAI reads the speech as Finnish. Whisper large still recognises the language itself, since Finnish on the HH server means Finnish Whisper.",
  },
  {
    id: "en",
    label: "English",
    hint: "Read as English.",
  },
];

// ---------------------------------------------------------------------------
// The models a recording can be transcribed with
// ---------------------------------------------------------------------------

export type EngineId = "hh-fi" | "hh-large" | "openai";

export interface Engine {
  id: EngineId;
  name: string;
  /** Where it runs. */
  where: string;
  note: string;
  /** The HH server times the text and can tell speakers apart. */
  server: boolean;
}

export const ENGINES: Engine[] = [
  {
    id: "hh-fi",
    name: "Finnish Whisper",
    where: "HH server",
    note: "Fine-tuned for Finnish; reads every recording as Finnish",
    server: true,
  },
  {
    id: "hh-large",
    name: "Whisper large",
    where: "HH server",
    note: "The general model, for any language",
    server: true,
  },
  {
    id: "openai",
    name: "OpenAI",
    where: "Azure",
    note: "Cloud model; the text without timestamps",
    server: false,
  },
];

export function engineById(id: EngineId): Engine {
  return ENGINES.find((engine) => engine.id === id) ?? ENGINES[0];
}

/**
 * The language and route of one model's run. The HH server switches to its
 * Finnish model when the language is Finnish, so Finnish Whisper always sends
 * "fi", and Whisper large never does: it recognises Finnish itself.
 */
export function engineRequest(
  engine: EngineId,
  language: Language,
): { language: Language; preferLocalFirst: boolean } {
  if (engine === "hh-fi") return { language: "fi", preferLocalFirst: true };
  if (engine === "hh-large")
    return {
      language: language === "en" ? "en" : "auto",
      preferLocalFirst: true,
    };
  return { language, preferLocalFirst: false };
}

/** Whether the language setting reaches any of these models. */
export function languageMatters(engines: EngineId[]): boolean {
  return engines.some((engine) => engine !== "hh-fi");
}

export interface TranscriberOptions {
  language: Language;
  /** The models to run, at the same time, in this order. */
  engines: EngineId[];
  diarization: boolean;
  speakerCount: string;
  minSpeakers: string;
  maxSpeakers: string;
  context: string;
  fixErrors: boolean;
  fixInstructions: string;
  compress: boolean;
}

export const DEFAULT_OPTIONS: TranscriberOptions = {
  language: "auto",
  engines: ["hh-fi"],
  diarization: false,
  speakerCount: "",
  minSpeakers: "",
  maxSpeakers: "",
  context: "",
  fixErrors: false,
  fixInstructions: "",
  compress: true,
};

export interface TranscriberExample {
  id: string;
  title: string;
  summary: string;
  url: string;
  fileName: string;
  /** What is special about it, for the card. */
  tags: string[];
  /** The options that show it off best. */
  options: Partial<TranscriberOptions>;
}

export const EXAMPLES: TranscriberExample[] = [
  {
    id: "note",
    title: "A short voice note",
    summary:
      "A 14-second Finnish note about a defect on a site, read by three models at once.",
    url: "/Sample11.m4a",
    fileName: "Sample11.m4a",
    tags: ["Finnish", "14 s", "3 models side by side"],
    options: { engines: ["hh-fi", "hh-large", "openai"] },
  },
  {
    id: "meeting",
    title: "A meeting with two speakers",
    summary:
      "A site meeting, spoken by two people. Speaker detection tells them apart and shows who spoke how much.",
    url: "/transcriber-examples/site-meeting-fi.mp3",
    fileName: "site-meeting-fi.mp3",
    tags: ["Finnish", "46 s", "2 speakers"],
    options: {
      engines: ["hh-fi"],
      diarization: true,
      minSpeakers: "2",
      maxSpeakers: "2",
    },
  },
  {
    id: "diary",
    title: "A site diary dictation",
    summary:
      "A Finnish dictation with names and numbers. Error fixing corrects the text, and you decide each change.",
    url: "/sample2.m4a",
    fileName: "sample2.m4a",
    tags: ["Finnish", "47 s", "fixed errors"],
    options: {
      engines: ["hh-fi"],
      fixErrors: true,
      context:
        "A construction site diary. The site is at Kometankuja 6. Terms: alihankkija, konekuljettaja, ulkoverhous.",
    },
  },
  {
    id: "consultation",
    title: "A consultation in English",
    summary:
      "A 93-second medical consultation summary, read by the HH server's general model and by OpenAI.",
    url: "/sample.mp3",
    fileName: "sample.mp3",
    tags: ["English", "93 s", "2 models"],
    options: { language: "en", engines: ["hh-large", "openai"] },
  },
];

// ---------------------------------------------------------------------------
// Reading a transcript
// ---------------------------------------------------------------------------

export interface Segment {
  start: number | null;
  end: number | null;
  speaker: string | null;
  text: string | null;
}

export interface DiffPart {
  kind: "equal" | "delete" | "insert" | "replace";
  original: string;
  corrected: string;
}

/** 83.4 -> "1:23", and 3723 -> "1:02:03". */
export function formatTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds))
    return "–";
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}`
    : `${minutes}:${rest}`;
}

export function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

const NO_SPEAKER = new Set(["", "UNKNOWN", "UNK"]);

/** Whether the segments say who spoke (and not just when). */
export function hasSpeakers(segments: Segment[]): boolean {
  return segments.some(
    (segment) => !NO_SPEAKER.has((segment.speaker ?? "").toUpperCase()),
  );
}

/** The speakers in the order they first speak, as "Speaker 1", "Speaker 2". */
export function speakerNames(segments: Segment[]): Map<string, string> {
  const names = new Map<string, string>();
  for (const segment of segments) {
    const key = segment.speaker ?? "UNKNOWN";
    if (NO_SPEAKER.has(key.toUpperCase()) || names.has(key)) continue;
    names.set(key, `Speaker ${names.size + 1}`);
  }
  return names;
}

export interface SpeakerStat {
  key: string;
  name: string;
  seconds: number;
  words: number;
  turns: number;
  /** Their part of the talk time, 0 to 1. */
  share: number;
}

export function speakerStats(segments: Segment[]): SpeakerStat[] {
  const names = speakerNames(segments);
  const stats = new Map<string, SpeakerStat>();
  let total = 0;
  let previous: string | null = null;
  for (const segment of segments) {
    const key = segment.speaker ?? "UNKNOWN";
    const name = names.get(key);
    if (!name) continue;
    const seconds = Math.max(0, (segment.end ?? 0) - (segment.start ?? 0));
    const entry = stats.get(key) ?? {
      key,
      name,
      seconds: 0,
      words: 0,
      turns: 0,
      share: 0,
    };
    entry.seconds += seconds;
    entry.words += wordCount(segment.text ?? "");
    if (previous !== key) entry.turns += 1;
    previous = key;
    total += seconds;
    stats.set(key, entry);
  }
  return [...stats.values()].map((entry) => ({
    ...entry,
    share: total > 0 ? entry.seconds / total : 0,
  }));
}

/** The index of the segment that is playing at a time, or -1. */
export function activeSegment(segments: Segment[], time: number): number {
  return segments.findIndex(
    (segment) =>
      segment.start !== null &&
      segment.end !== null &&
      time >= segment.start &&
      time < segment.end,
  );
}

/** The transcript as lines "[0:03] Speaker 1: text", for copying or saving. */
export function segmentsToText(segments: Segment[]): string {
  const names = speakerNames(segments);
  return segments
    .map((segment) => {
      const who = names.get(segment.speaker ?? "UNKNOWN");
      return `[${formatTime(segment.start)}]${who ? ` ${who}:` : ""} ${(segment.text ?? "").trim()}`;
    })
    .join("\n");
}

/** The positions of the parts that differ between the raw and corrected text. */
export function changedParts(parts: DiffPart[]): number[] {
  return parts.flatMap((part, index) => (part.kind === "equal" ? [] : [index]));
}

/** The text made by taking the correction for the accepted changes and the original for the rest. */
export function applyChanges(parts: DiffPart[], accepted: Set<number>): string {
  return parts
    .map((part, index) =>
      part.kind === "equal"
        ? part.original
        : accepted.has(index)
          ? part.corrected
          : part.original,
    )
    .filter((text) => text !== "")
    .join(" ");
}

export function downloadName(filename: string, suffix: string): string {
  const stem = filename.replace(/\.[^.]+$/, "") || "transcript";
  return `${stem}${suffix}`;
}

/** A word as the comparison sees it: lower-cased, without punctuation. */
function comparable(word: string): string {
  return word.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}

/** Longest texts whose word differences are marked (base words x other words). */
export const MAX_DIFF_CELLS = 4_000_000;

/**
 * For each word of `other`, whether it is missing from the shared run of words
 * with `base` (a longest common subsequence, case and punctuation ignored).
 * Null when the texts are too long to compare in the browser.
 */
export function differingWords(base: string, other: string): boolean[] | null {
  const a = base.split(/\s+/).filter(Boolean).map(comparable);
  const words = other.split(/\s+/).filter(Boolean);
  const b = words.map(comparable);
  if (a.length * b.length > MAX_DIFF_CELLS) return null;
  const width = b.length + 1;
  const lengths = new Uint16Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      lengths[i * width + j] =
        a[i] === b[j]
          ? lengths[(i + 1) * width + j + 1] + 1
          : Math.max(lengths[(i + 1) * width + j], lengths[i * width + j + 1]);
  const differs = b.map((word) => word !== "");
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      differs[j] = false;
      i++;
      j++;
    } else if (lengths[(i + 1) * width + j] >= lengths[i * width + j + 1]) i++;
    else j++;
  }
  return differs;
}
