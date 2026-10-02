import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
  EXAMPLES,
  activeSegment,
  applyChanges,
  changedParts,
  formatTime,
  hasSpeakers,
  segmentsToText,
  speakerNames,
  speakerStats,
  wordCount,
  type DiffPart,
  type Segment,
} from "./transcriber-data";

const seg = (
  start: number,
  end: number,
  speaker: string | null,
  text: string,
): Segment => ({ start, end, speaker, text });

const TALK: Segment[] = [
  seg(0, 4, "SPEAKER_01", "Hello there everyone"),
  seg(4, 6, "SPEAKER_00", "Thanks"),
  seg(6, 12, "SPEAKER_01", "Let us begin the meeting"),
];

test("every example file exists", () => {
  for (const example of EXAMPLES) {
    expect(existsSync(`public${example.url}`)).toBe(true);
    expect(example.url.endsWith(example.fileName)).toBe(true);
  }
});

test("formatTime", () => {
  expect(formatTime(0)).toBe("0:00");
  expect(formatTime(83.4)).toBe("1:23");
  expect(formatTime(3723)).toBe("1:02:03");
  expect(formatTime(null)).toBe("–");
});

test("wordCount", () => {
  expect(wordCount("  a  b\nc ")).toBe(3);
  expect(wordCount("")).toBe(0);
});

describe("speakers", () => {
  test("named in the order they first speak", () => {
    expect([...speakerNames(TALK).values()]).toEqual([
      "Speaker 1",
      "Speaker 2",
    ]);
    expect(speakerNames(TALK).get("SPEAKER_01")).toBe("Speaker 1");
  });
  test("timed segments without a speaker are not a conversation", () => {
    expect(hasSpeakers([seg(0, 1, "UNKNOWN", "a"), seg(1, 2, null, "b")])).toBe(
      false,
    );
    expect(hasSpeakers(TALK)).toBe(true);
  });
  test("talk time, words, turns and shares", () => {
    const [first, second] = speakerStats(TALK);
    expect(first.name).toBe("Speaker 1");
    expect(first.seconds).toBe(10);
    expect(first.words).toBe(8);
    expect(first.turns).toBe(2);
    expect(second.seconds).toBe(2);
    expect(first.share + second.share).toBeCloseTo(1);
  });
});

test("activeSegment finds the segment that is playing", () => {
  expect(activeSegment(TALK, 0)).toBe(0);
  expect(activeSegment(TALK, 5.9)).toBe(1);
  expect(activeSegment(TALK, 12)).toBe(-1);
});

test("segmentsToText labels the speakers", () => {
  expect(segmentsToText(TALK).split("\n")[1]).toBe("[0:04] Speaker 2: Thanks");
  expect(segmentsToText([seg(65, 70, "UNKNOWN", " x ")])).toBe("[1:05] x");
});

describe("reviewing the changes", () => {
  const parts: DiffPart[] = [
    { kind: "equal", original: "Hello", corrected: "Hello" },
    { kind: "replace", original: "wrold", corrected: "world" },
    { kind: "equal", original: "and", corrected: "and" },
    { kind: "delete", original: "uh", corrected: "" },
    { kind: "insert", original: "", corrected: "everyone" },
  ];
  test("lists only the parts that differ", () => {
    expect(changedParts(parts)).toEqual([1, 3, 4]);
  });
  test("accepting all gives the corrected text", () => {
    expect(applyChanges(parts, new Set([1, 3, 4]))).toBe(
      "Hello world and everyone",
    );
  });
  test("accepting none gives the original text", () => {
    expect(applyChanges(parts, new Set())).toBe("Hello wrold and uh");
  });
  test("accepting some mixes the two", () => {
    expect(applyChanges(parts, new Set([1]))).toBe("Hello world and uh");
  });
});
