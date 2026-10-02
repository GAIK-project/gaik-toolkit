import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { writingOrder, knowledgeId } from "@/lib/knowledge-synthesis/workspace";
import {
  EXAMPLES,
  citationCounts,
  figuresOf,
  missingMarkers,
  sourceFilesOf,
  wordCount,
} from "./synthesis-data";

describe("the examples", () => {
  for (const example of EXAMPLES) {
    test(`${example.id}: knowledge exists and every base section has knowledge`, () => {
      expect(existsSync(`public${example.url}`)).toBe(true);
      const knowledge = JSON.parse(
        readFileSync(`public${example.url}`, "utf-8"),
      ) as Record<string, string>;
      const ids = Object.keys(knowledge).map(knowledgeId);
      for (const section of example.sections.filter(
        (s) => s.depends_on.length === 0,
      ))
        expect(ids).toContain(section.id);
    });
    test(`${example.id}: the writing order is valid, with the derived section last`, () => {
      const order = writingOrder(example.sections);
      expect(order).not.toBeNull();
      expect(order!.length).toBe(2);
      expect(order![1]).toHaveLength(1);
    });
  }
  test("only the second example has a sample report", () => {
    expect(EXAMPLES[0].sample).toBeNull();
    expect(EXAMPLES[1].sample?.text.length).toBeGreaterThan(100);
  });
});

test("wordCount", () => {
  expect(wordCount(" a b\nc ")).toBe(3);
  expect(wordCount("")).toBe(0);
});

test("citationCounts counts the files that are named", () => {
  const text = "A (notes.txt). B (notes.txt, row 3). C (log.csv).";
  expect(citationCounts(text, ["notes.txt", "log.csv", "other.pdf"])).toEqual([
    ["notes.txt", 2],
    ["log.csv", 1],
  ]);
});

test("missingMarkers lists what no source covers", () => {
  expect(
    missingMarkers(
      "Roof is old. (missing: gutter condition) Wall. (Missing: x)",
    ),
  ).toEqual(["gutter condition", "x"]);
});

test("figuresOf gives words, citations and missing markers per section", () => {
  expect(
    figuresOf(
      [{ id: "a", text: "One two (notes.txt) (missing: y)" }],
      ["notes.txt"],
    ),
  ).toEqual([{ id: "a", words: 5, citations: 1, missing: 1 }]);
});

test("sourceFilesOf reads the files the facts cite and skips bad JSON", () => {
  const knowledge = JSON.stringify({
    units: [
      { source: { file: "b.txt" } },
      { source: { file: "a.csv" } },
      { source: { file: "b.txt" } },
    ],
  });
  expect(sourceFilesOf([knowledge, "not json"])).toEqual(["a.csv", "b.txt"]);
});
