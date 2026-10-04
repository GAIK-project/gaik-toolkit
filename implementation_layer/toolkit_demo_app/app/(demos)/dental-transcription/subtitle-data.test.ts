import { existsSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "bun:test";
import {
  activeCue,
  EXAMPLES,
  isFast,
  parseSrt,
  regroup,
  saveName,
  searchCues,
  shiftCues,
  speakerNames,
  statsOf,
  toSrt,
  toText,
  toVtt,
  type Cue,
  type RawSegment,
} from "./subtitle-data";

const PUBLIC = join(import.meta.dir, "../../../public");

const words = (text: string, from: number, step = 0.5) =>
  text.split(" ").map((word, index) => ({
    start: from + index * step,
    end: from + (index + 1) * step - 0.05,
    text: word,
  }));

const segment: RawSegment = {
  start: 0,
  end: 4,
  text: "Hello there and welcome to the long lecture today",
  speaker: "SPEAKER_01",
  words: words("Hello there and welcome to the long lecture today", 0, 0.4),
};

test("every example recording exists", () => {
  for (const example of EXAMPLES)
    if (example.url) expect(existsSync(join(PUBLIC, example.url))).toBe(true);
});

test("a long segment is cut between words, each part timed by its own words", () => {
  const cues = regroup([segment], 24);
  expect(cues.length).toBeGreaterThan(1);
  for (const cue of cues) expect(cue.text.length).toBeLessThanOrEqual(24);
  expect(cues.map((cue) => cue.text).join(" ")).toBe(segment.text);
  expect(cues[0].start).toBe(0);
  expect(cues[0].end).toBeLessThan(cues[1].start);
  expect(cues.every((cue) => cue.speaker === "Speaker 1")).toBe(true);
});

test("segments stay whole as spoken, or without word times, or when short", () => {
  expect(regroup([segment], 0)).toHaveLength(1);
  expect(regroup([segment], 200)).toHaveLength(1);
  expect(regroup([{ ...segment, words: [] }], 10)).toHaveLength(1);
  expect(regroup([{ ...segment, start: null }], 0)).toHaveLength(0);
  expect(regroup([{ ...segment, text: "  " }], 0)).toHaveLength(0);
});

test("a word longer than the limit stands alone", () => {
  const cues = regroup(
    [
      {
        start: 0,
        end: 3,
        text: "a extraordinarily b",
        words: words("a extraordinarily b", 0, 1),
      },
    ],
    6,
  );
  expect(cues.map((cue) => cue.text)).toEqual(["a", "extraordinarily", "b"]);
});

test("speakers are named by order of appearance, unknown ones have no name", () => {
  const names = speakerNames([
    { start: 0, end: 1, text: "a", speaker: "SPEAKER_01" },
    { start: 1, end: 2, text: "b", speaker: "UNKNOWN" },
    { start: 2, end: 3, text: "c", speaker: "SPEAKER_00" },
    { start: 3, end: 4, text: "d", speaker: "SPEAKER_01" },
  ]);
  expect(names.get("SPEAKER_01")).toBe("Speaker 1");
  expect(names.get("SPEAKER_00")).toBe("Speaker 2");
  expect(names.has("UNKNOWN")).toBe(false);
});

const cues: Cue[] = [
  { start: 0.031, end: 1.574, text: "Hei, tässä Jari.", speaker: "Speaker 1" },
  {
    start: 3725.5,
    end: 3727,
    text: "Asia vaatii korjausta.",
    speaker: "Speaker 2",
  },
];

test("SRT and VTT carry the times and, when asked, the speakers", () => {
  const srt = toSrt(cues);
  expect(srt).toContain("1\n00:00:00,031 --> 00:00:01,574\nHei, tässä Jari.");
  expect(srt).toContain("2\n01:02:05,500 --> 01:02:07,000");
  expect(toSrt(cues, true)).toContain("[Speaker 1] Hei, tässä Jari.");
  const vtt = toVtt(cues, true);
  expect(vtt.startsWith("WEBVTT\n\n")).toBe(true);
  expect(vtt).toContain("00:00:00.031 --> 00:00:01.574\n[Speaker 1] Hei");
});

test("an SRT text is read back into the same subtitles", () => {
  const back = parseSrt(toSrt(cues));
  expect(back).toHaveLength(2);
  expect(back[0]).toMatchObject({
    start: 0.031,
    end: 1.574,
    text: "Hei, tässä Jari.",
  });
  expect(back[1].start).toBeCloseTo(3725.5, 3);
  expect(parseSrt(toVtt(cues))).toHaveLength(2);
  expect(parseSrt("not subtitles at all")).toEqual([]);
  expect(
    parseSrt("1\r\n00:00:01,000 --> 00:00:02,000\r\nTwo\r\nlines\r\n")[0].text,
  ).toBe("Two lines");
});

test("the text, with and without speakers", () => {
  expect(toText(cues)).toBe("Hei, tässä Jari. Asia vaatii korjausta.");
  expect(toText(cues, true)).toBe(
    "Speaker 1: Hei, tässä Jari.\nSpeaker 2: Asia vaatii korjausta.",
  );
  const same = [cues[0], { ...cues[0], text: "Toinen." }];
  expect(toText(same, true)).toBe("Speaker 1: Hei, tässä Jari. Toinen.");
});

test("shifting moves every time, and none goes below zero", () => {
  const moved = shiftCues(cues, -1);
  expect(moved[0].start).toBe(0);
  expect(moved[1].start).toBeCloseTo(3724.5, 3);
  expect(shiftCues(cues, 2)[0].end).toBeCloseTo(3.574, 3);
});

test("the subtitle shown at a time, and none between two", () => {
  expect(activeCue(cues, 1)).toBe(0);
  expect(activeCue(cues, 2)).toBe(-1);
  expect(activeCue(cues, 3726)).toBe(1);
  expect(activeCue(cues, 1.574)).toBe(-1);
});

test("reading speed flags subtitles that go by too fast", () => {
  expect(
    isFast({ start: 0, end: 1, text: "x".repeat(30), speaker: null }),
  ).toBe(true);
  expect(
    isFast({ start: 0, end: 3, text: "x".repeat(30), speaker: null }),
  ).toBe(false);
  expect(isFast({ start: 1, end: 1, text: "x", speaker: null })).toBe(true);
});

test("search ignores case and counts nothing for an empty query", () => {
  expect(searchCues(cues, "ASIA")).toEqual([1]);
  expect(searchCues(cues, " ")).toEqual([]);
  expect(searchCues(cues, "zzz")).toEqual([]);
});

test("statistics and file names", () => {
  expect(statsOf(cues)).toMatchObject({ count: 2, words: 6, duration: 3727 });
  expect(saveName("my.video.mp4", "srt")).toBe("my.video.srt");
  expect(saveName("", "vtt")).toBe("subtitles.vtt");
});
