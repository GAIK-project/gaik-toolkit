// What the Video Transcription & Subtitles demo works with: ready-made recordings, and how
// the timed segments of a transcription become subtitles that can be regrouped, shifted,
// searched and saved as SRT and VTT.

import { formatTime } from "../transcriber/transcriber-data";

export interface Word {
  start: number;
  end: number;
  text: string;
}

/** One piece of speech as the transcription service returns it. */
export interface RawSegment {
  start: number | null;
  end: number | null;
  text: string;
  speaker?: string | null;
  words?: Word[];
}

/** One subtitle: shown from start to end. */
export interface Cue {
  start: number;
  end: number;
  text: string;
  /** "Speaker 1", or null when the speakers were not told apart. */
  speaker: string | null;
}

export interface SubtitleExample {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  /** A ready-made recording the service reads when you press Transcribe. */
  url?: string;
  fileName?: string;
  language: string;
  diarization?: boolean;
  speakers?: string;
}

export const LANGUAGES = [
  { id: "auto", label: "Auto-detect" },
  { id: "fi", label: "Finnish (Suomi)" },
  { id: "en", label: "English" },
  { id: "sv", label: "Swedish (Svenska)" },
];

export const EXAMPLES: SubtitleExample[] = [
  {
    id: "note",
    title: "A short voice note",
    summary:
      "A 14-second Finnish note about a defect on a site. The quickest way to see subtitles made.",
    tags: ["Finnish", "14 s", "quick"],
    url: "/Sample11.m4a",
    fileName: "Sample11.m4a",
    language: "fi",
  },
  {
    id: "meeting",
    title: "A meeting with two speakers",
    summary:
      "A site meeting in Finnish. With speaker detection, every subtitle names who speaks, and you can leave the names out of the file.",
    tags: ["Finnish", "46 s", "2 speakers"],
    url: "/transcriber-examples/site-meeting-fi.mp3",
    fileName: "site-meeting-fi.mp3",
    language: "fi",
    diarization: true,
    speakers: "2",
  },
  {
    id: "consultation",
    title: "A consultation in English",
    summary:
      "A 93-second medical consultation summary. Try the subtitle length: short subtitles of about 42 characters read well on a screen.",
    tags: ["English", "93 s", "regroup"],
    url: "/sample.mp3",
    fileName: "sample.mp3",
    language: "en",
  },
];

// ---------------------------------------------------------------------------
// Subtitle length
// ---------------------------------------------------------------------------

/** How long a subtitle may be, in characters. 0 keeps the segments as they were spoken. */
export const LENGTHS: { value: number; label: string; hint: string }[] = [
  {
    value: 0,
    label: "As spoken",
    hint: "One subtitle for each segment of speech.",
  },
  {
    value: 32,
    label: "Short (32)",
    hint: "Fits a phone screen or a narrow video.",
  },
  {
    value: 42,
    label: "Standard (42)",
    hint: "The usual line length of broadcast subtitles.",
  },
  {
    value: 70,
    label: "Long (70)",
    hint: "Two short lines, for a wide screen.",
  },
];

const clean = (text: string): string => text.replace(/\s+/g, " ").trim();

/** "SPEAKER_00" becomes "Speaker 1" by order of appearance; unknown speakers have no name. */
export function speakerNames(segments: RawSegment[]): Map<string, string> {
  const names = new Map<string, string>();
  for (const segment of segments) {
    const raw = segment.speaker;
    if (!raw || /^unknown$/i.test(raw) || names.has(raw)) continue;
    names.set(raw, `Speaker ${names.size + 1}`);
  }
  return names;
}

/**
 * The subtitles of some segments. With a length, a segment longer than it is cut between words,
 * and every part is timed by its own words; a segment without word times stays whole.
 */
export function regroup(segments: RawSegment[], maxChars: number): Cue[] {
  const names = speakerNames(segments);
  const cues: Cue[] = [];
  for (const segment of segments) {
    if (segment.start === null || segment.end === null) continue;
    const text = clean(segment.text);
    if (!text) continue;
    const speaker = segment.speaker
      ? (names.get(segment.speaker) ?? null)
      : null;
    const words = segment.words ?? [];
    if (maxChars <= 0 || text.length <= maxChars || words.length < 2) {
      cues.push({ start: segment.start, end: segment.end, text, speaker });
      continue;
    }
    let group: Word[] = [];
    let length = 0;
    const flush = () => {
      if (group.length === 0) return;
      cues.push({
        start: group[0].start,
        end: group[group.length - 1].end,
        text: clean(group.map((word) => word.text).join(" ")),
        speaker,
      });
      group = [];
      length = 0;
    };
    for (const word of words) {
      const wordLength = clean(word.text).length;
      if (group.length > 0 && length + 1 + wordLength > maxChars) flush();
      group.push(word);
      length += (group.length > 1 ? 1 : 0) + wordLength;
    }
    flush();
  }
  return cues;
}

// ---------------------------------------------------------------------------
// Reading and writing subtitle files
// ---------------------------------------------------------------------------

const TIME = /(\d+):(\d{2}):(\d{2})[,.](\d{1,3})/;

function seconds(match: RegExpMatchArray): number {
  // Whole milliseconds first: adding fractions of a second gives 1.5739999999999998.
  const whole =
    Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
  return (whole * 1000 + Number(match[4].padEnd(3, "0"))) / 1000;
}

/** Reads an SRT (or VTT) text into subtitles; blocks that are not subtitles are skipped. */
export function parseSrt(text: string): Cue[] {
  const cues: Cue[] = [];
  for (const block of text.replace(/\r\n?/g, "\n").split(/\n{2,}/)) {
    const lines = block.split("\n").filter((line) => line.trim() !== "");
    const at = lines.findIndex((line) => line.includes("-->"));
    if (at === -1) continue;
    const [from, to] = lines[at].split("-->");
    const start = from.match(TIME);
    const end = to.match(TIME);
    if (!start || !end) continue;
    const body = clean(lines.slice(at + 1).join(" "));
    if (!body) continue;
    cues.push({
      start: seconds(start),
      end: seconds(end),
      text: body,
      speaker: null,
    });
  }
  return cues;
}

function stamp(value: number, separator: "," | "."): string {
  const total = Math.max(0, Math.round(value * 1000));
  const ms = total % 1000;
  const s = Math.floor(total / 1000) % 60;
  const m = Math.floor(total / 60000) % 60;
  const h = Math.floor(total / 3600000);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${two(h)}:${two(m)}:${two(s)}${separator}${String(ms).padStart(3, "0")}`;
}

const lineOf = (cue: Cue, withSpeakers: boolean): string =>
  withSpeakers && cue.speaker ? `[${cue.speaker}] ${cue.text}` : cue.text;

export function toSrt(cues: Cue[], withSpeakers = false): string {
  return cues
    .map(
      (cue, index) =>
        `${index + 1}\n${stamp(cue.start, ",")} --> ${stamp(cue.end, ",")}\n${lineOf(cue, withSpeakers)}\n`,
    )
    .join("\n");
}

export function toVtt(cues: Cue[], withSpeakers = false): string {
  const body = cues
    .map(
      (cue) =>
        `${stamp(cue.start, ".")} --> ${stamp(cue.end, ".")}\n${lineOf(cue, withSpeakers)}\n`,
    )
    .join("\n");
  return `WEBVTT\n\n${body}`;
}

/** The text alone; with speakers, a new line starts when the speaker changes. */
export function toText(cues: Cue[], withSpeakers = false): string {
  if (!withSpeakers) return cues.map((cue) => cue.text).join(" ");
  const lines: string[] = [];
  let speaker: string | null | undefined;
  for (const cue of cues) {
    if (cue.speaker !== speaker || lines.length === 0) {
      lines.push(cue.speaker ? `${cue.speaker}: ${cue.text}` : cue.text);
      speaker = cue.speaker;
    } else {
      lines[lines.length - 1] += ` ${cue.text}`;
    }
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Working with the subtitles
// ---------------------------------------------------------------------------

/** All the subtitles moved in time; none starts before 0. */
export function shiftCues(cues: Cue[], by: number): Cue[] {
  return cues.map((cue) => ({
    ...cue,
    start: Math.max(0, cue.start + by),
    end: Math.max(0, cue.end + by),
  }));
}

/** The index of the subtitle shown at a time, or -1 between two subtitles. */
export function activeCue(cues: Cue[], time: number): number {
  return cues.findIndex((cue) => time >= cue.start && time < cue.end);
}

/** Characters read each second: above about 20, a subtitle is hard to read in time. */
export function readingSpeed(cue: Cue): number {
  const duration = cue.end - cue.start;
  return duration > 0 ? cue.text.length / duration : Number.POSITIVE_INFINITY;
}

export const FAST_READING = 20;
export const isFast = (cue: Cue): boolean => readingSpeed(cue) > FAST_READING;

/** The indexes of the subtitles that hold the text, ignoring case. */
export function searchCues(cues: Cue[], query: string): number[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return cues.flatMap((cue, index) =>
    cue.text.toLowerCase().includes(needle) ? [index] : [],
  );
}

export interface CueStats {
  count: number;
  words: number;
  duration: number;
  fast: number;
}

export function statsOf(cues: Cue[]): CueStats {
  return {
    count: cues.length,
    words: cues.reduce(
      (sum, cue) => sum + (cue.text.match(/\S+/g)?.length ?? 0),
      0,
    ),
    duration: cues.reduce((latest, cue) => Math.max(latest, cue.end), 0),
    fast: cues.filter(isFast).length,
  };
}

export const clock = (value: number): string => formatTime(value);

/** A file name for what is saved: the recording's name with the extension replaced. */
export function saveName(fileName: string, extension: string): string {
  const base = fileName.replace(/\.[^.]+$/, "") || "subtitles";
  return `${base}.${extension}`;
}
