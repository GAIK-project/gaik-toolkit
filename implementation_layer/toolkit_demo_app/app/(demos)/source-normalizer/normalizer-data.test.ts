import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
  EXAMPLES,
  countByClass,
  describeText,
  hasImages,
  hasRecordings,
  kindOf,
  progressShare,
} from "./normalizer-data";

describe("kindOf", () => {
  test("local converters call no model", () => {
    for (const name of ["a.pdf", "b.DOCX", "c.xlsx", "d.csv", "e.txt", "f.md"])
      expect(kindOf(name).usesModel).toBe(false);
  });
  test("recordings and images call a model", () => {
    expect(kindOf("rec.mp3")).toMatchObject({
      label: "Recording",
      tool: "Transcriber",
      usesModel: true,
    });
    expect(kindOf("plan.PNG")).toMatchObject({
      label: "Image",
      tool: "VisionParser",
      usesModel: true,
    });
  });
  test("other files are unknown", () => {
    expect(kindOf("slides.pptx").label).toBe("Unknown");
    expect(kindOf("noextension").label).toBe("Unknown");
  });
});

test("hasRecordings and hasImages", () => {
  expect(hasRecordings(["a.pdf", "b.m4a"])).toBe(true);
  expect(hasRecordings(["a.pdf", "b.png"])).toBe(false);
  expect(hasImages(["b.jpeg"])).toBe(true);
  expect(hasImages([])).toBe(false);
});

test("every example file exists in public/", () => {
  for (const example of EXAMPLES)
    for (const file of example.files)
      expect(existsSync(`public${file.url}`)).toBe(true);
});

test("describeText", () => {
  expect(describeText("a b\nc")).toEqual({ chars: 5, words: 3, lines: 2 });
  expect(describeText("")).toEqual({ chars: 0, words: 0, lines: 0 });
});

test("countByClass", () => {
  expect(
    countByClass([
      { source_class: "primary" },
      { source_class: "primary" },
      { source_class: null },
    ]),
  ).toEqual({ primary: 2, unlabelled: 1 });
});

test("progressShare stays between 0 and 1", () => {
  expect(progressShare(1, 4)).toBe(0.25);
  expect(progressShare(9, 4)).toBe(1);
  expect(progressShare(1, 0)).toBe(0);
});
