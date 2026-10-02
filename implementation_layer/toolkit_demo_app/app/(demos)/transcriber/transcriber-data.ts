// What the Transcriber demo works with: the options and what each does, ready-made
// recordings with the options that suit them, and how a transcript is read.

export type Language = "auto" | "fi" | "en";

export const LANGUAGES: { id: Language; label: string; hint: string }[] = [
  {
    id: "auto",
    label: "Auto-detect",
    hint: "The language is recognised from the speech. A good choice when it varies or is not known.",
  },
  {
    id: "fi",
    label: "Finnish",
    hint: "Uses the Finnish speech model of the HH server, which is more accurate for Finnish than the general one.",
  },
  {
    id: "en",
    label: "English",
    hint: "Reads the speech as English, with the general large model of the HH server.",
  },
];

export interface TranscriberOptions {
  language: Language;
  /** Try the HH Whisper server first; the cloud model is the fallback. */
  preferLocalFirst: boolean;
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
  preferLocalFirst: true,
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
      "A 14-second Finnish note about a defect on a site. The quickest way to see the result.",
    url: "/Sample11.m4a",
    fileName: "Sample11.m4a",
    tags: ["Finnish", "14 s", "timed text"],
    options: { language: "fi" },
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
      language: "fi",
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
      language: "fi",
      fixErrors: true,
      context:
        "A construction site diary. The site is at Kometankuja 6. Terms: alihankkija, konekuljettaja, ulkoverhous.",
    },
  },
  {
    id: "consultation",
    title: "A consultation in English",
    summary:
      "A 93-second medical consultation summary. Turn the HH server off to read it with the cloud model instead.",
    url: "/sample.mp3",
    fileName: "sample.mp3",
    tags: ["English", "93 s"],
    options: { language: "en" },
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
