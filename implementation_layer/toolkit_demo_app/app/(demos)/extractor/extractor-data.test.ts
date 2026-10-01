import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
  EXAMPLES,
  PARSERS,
  DEFAULT_PARSER,
  cellText,
  columnsOf,
  countFound,
  isEmptyValue,
} from "./extractor-data";

describe("isEmptyValue", () => {
  test("treats null, empty text and empty lists as nothing found", () => {
    expect(isEmptyValue(null)).toBe(true);
    expect(isEmptyValue("  ")).toBe(true);
    expect(isEmptyValue([])).toBe(true);
    expect(isEmptyValue([null, ""])).toBe(true);
  });
  test("keeps zero, false and filled values", () => {
    expect(isEmptyValue(0)).toBe(false);
    expect(isEmptyValue(false)).toBe(false);
    expect(isEmptyValue(["a"])).toBe(false);
  });
});

test("countFound counts the filled top-level fields", () => {
  expect(countFound({ a: "x", b: null, c: [], d: 0 })).toEqual({
    found: 2,
    total: 4,
  });
});

test("columnsOf lists every key once, in order of appearance", () => {
  expect(
    columnsOf([
      { a: 1, b: 2 },
      { b: 3, c: 4 },
    ]),
  ).toEqual(["a", "b", "c"]);
});

test("cellText flattens a value to one line", () => {
  expect(cellText(null)).toBe("");
  expect(cellText(["a", "b"])).toBe("a, b");
  expect(cellText({ a: 1 })).toBe('{"a":1}');
  expect(cellText(12.5)).toBe("12.5");
});

describe("the parsers", () => {
  test("auto is the default and the first choice", () => {
    expect(DEFAULT_PARSER).toBe("auto");
    expect(PARSERS[0].id).toBe("auto");
  });
  test("offers the seven parsers of the Parser demo", () => {
    expect(PARSERS.map((p) => p.id)).toEqual([
      "auto",
      "pymupdf",
      "docx",
      "vision",
      "vision_plus",
      "docling_api",
      "multimodal",
    ]);
  });
});

test("every example is a real file in public/ with a real task", () => {
  expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length);
  for (const example of EXAMPLES) {
    expect(example.task.length).toBeGreaterThan(200);
    expect(example.url.endsWith(example.fileName)).toBe(true);
    expect(existsSync(`public${example.url}`)).toBe(true);
  }
});
