import { describe, expect, test } from "bun:test";
import {
  EXAMPLES,
  MAX_CHARACTERS,
  MAX_PART_CHARACTERS,
  VOICES,
  estimateSeconds,
  formatDuration,
  joinBytes,
  splitForSpeech,
  wordCount,
} from "./tts-data";

describe("splitForSpeech", () => {
  test("keeps a short text whole", () => {
    expect(splitForSpeech("Hello there. How are you?")).toEqual([
      "Hello there. How are you?",
    ]);
  });
  test("does not split a date or a number", () => {
    const parts = splitForSpeech("Päivämäärä 10.04.2025. Kohde 4120-01.", 20);
    expect(parts.join(" ")).toBe("Päivämäärä 10.04.2025. Kohde 4120-01.");
    expect(parts.some((part) => part.includes("10.04.2025"))).toBe(true);
  });
  test("splits between sentences, never past the limit", () => {
    const text = "Aaaa bbbb. Cccc dddd. Eeee ffff. Gggg hhhh.";
    const parts = splitForSpeech(text, 24);
    expect(parts).toEqual(["Aaaa bbbb. Cccc dddd.", "Eeee ffff. Gggg hhhh."]);
    for (const part of parts) expect(part.length).toBeLessThanOrEqual(24);
  });
  test("cuts a sentence longer than the limit at a space", () => {
    const parts = splitForSpeech("one two three four five six seven eight", 15);
    for (const part of parts) expect(part.length).toBeLessThanOrEqual(15);
    expect(parts.join(" ")).toBe("one two three four five six seven eight");
  });
  test("a blank text has no parts", () => {
    expect(splitForSpeech("  \n ")).toEqual([]);
  });
});

test("the examples fit the demo's limits", () => {
  expect(EXAMPLES).toHaveLength(2);
  for (const example of EXAMPLES) {
    expect(example.text.length).toBeLessThanOrEqual(MAX_CHARACTERS);
    for (const part of splitForSpeech(example.text))
      expect(part.length).toBeLessThanOrEqual(MAX_PART_CHARACTERS);
    for (const voice of example.voices)
      expect(VOICES.map((v) => v.id)).toContain(voice);
  }
});

test("the second example is long enough to be read in parts", () => {
  expect(splitForSpeech(EXAMPLES[1].text).length).toBeGreaterThan(1);
});

test("timing", () => {
  expect(wordCount(" a b  c ")).toBe(3);
  expect(estimateSeconds("word ".repeat(150), "en")).toBe(60);
  expect(estimateSeconds("sana ".repeat(125), "fi")).toBe(60);
  expect(formatDuration(75.4)).toBe("1:15");
  expect(formatDuration(null)).toBe("–");
});

test("joinBytes puts the parts one after the other", () => {
  expect([...joinBytes([new Uint8Array([1, 2]), new Uint8Array([3])])]).toEqual(
    [1, 2, 3],
  );
});
