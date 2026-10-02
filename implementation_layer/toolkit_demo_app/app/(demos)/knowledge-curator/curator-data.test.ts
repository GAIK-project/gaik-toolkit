import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import {
  EXAMPLES,
  NO_FILTER,
  allFacts,
  countBy,
  findQuote,
  matchesFilter,
  totalsOf,
} from "./curator-data";
import type { SectionKnowledge } from "@/lib/knowledge-curator/workspace";

const unit = (
  id: string,
  over: Partial<SectionKnowledge["units"][0]> = {},
) => ({
  id,
  topic: "Roof",
  time_qualifier: null,
  summary: "The roof leaks",
  quote: "rainwater stains",
  source: { file: "notes.txt", locator: null },
  source_class: "primary",
  confidence: "high",
  ...over,
});

const KNOWLEDGE: SectionKnowledge[] = [
  {
    section_id: "roof",
    units: [
      unit("u1"),
      unit("u2", {
        confidence: "low",
        source: { file: "log.csv", locator: "row 3" },
        source_class: "secondary",
      }),
    ],
    missing: ["gutters"],
    conflicts: [
      {
        topic: "age",
        description: "d",
        status: "resolved",
        unit_ids: ["u1", "u2"],
      },
    ],
  },
  {
    section_id: "wall",
    units: [unit("u3", { topic: "Wall", summary: "Damp", quote: "18 %" })],
    missing: [],
    conflicts: [
      {
        topic: "damp",
        description: "d",
        status: "unresolved",
        unit_ids: ["u3"],
      },
    ],
  },
];

describe("findQuote", () => {
  test("finds the words whatever the spacing and case", () => {
    const text = "Roof\n- Rainwater   stains on the\nattic floor.";
    const found = findQuote(text, "rainwater stains on the attic floor");
    expect(found).not.toBeNull();
    expect(text.slice(found!.start, found!.end)).toBe(
      "Rainwater   stains on the\nattic floor",
    );
  });
  test("sees through ligatures", () => {
    const text = "The roof contractor Holm Rooﬁng arrived.";
    const found = findQuote(text, "Holm Roofing");
    expect(found && text.slice(found.start, found.end)).toBe("Holm Rooﬁng");
  });
  test("returns null when the words are not there", () => {
    expect(findQuote("abc def", "xyz")).toBeNull();
    expect(findQuote("abc", "  ")).toBeNull();
  });
});

describe("the facts", () => {
  const facts = allFacts(KNOWLEDGE);
  test("every fact knows its topic file", () => {
    expect(facts.map((f) => f.sectionId)).toEqual(["roof", "roof", "wall"]);
  });
  test("filters by text, confidence, file and class", () => {
    const count = (filter: Partial<typeof NO_FILTER>) =>
      facts.filter((f) => matchesFilter(f, { ...NO_FILTER, ...filter })).length;
    expect(count({})).toBe(3);
    expect(count({ query: "DAMP" })).toBe(1);
    expect(count({ query: "18 %" })).toBe(1);
    expect(count({ confidence: "low" })).toBe(1);
    expect(count({ file: "notes.txt" })).toBe(2);
    expect(count({ sourceClass: "secondary" })).toBe(1);
  });
  test("totals count topics, facts, missing and conflicts", () => {
    expect(totalsOf(KNOWLEDGE)).toEqual({
      topics: 2,
      facts: 3,
      missing: 1,
      conflicts: 2,
      unresolved: 1,
    });
  });
  test("countBy counts and sorts", () => {
    expect(countBy(facts, (f) => f.source.file)).toEqual([
      ["notes.txt", 2],
      ["log.csv", 1],
    ]);
  });
});

describe("the examples", () => {
  test("their sources exist, are valid, and every quote-able fact source is a text", () => {
    for (const example of EXAMPLES) {
      expect(existsSync(`public${example.url}`)).toBe(true);
      const artifacts = JSON.parse(
        readFileSync(`public${example.url}`, "utf-8"),
      ) as Record<string, string>;
      expect(Object.keys(artifacts)).toContain("normalized/sources.json");
      const files = JSON.parse(artifacts["normalized/sources.json"]) as {
        id: string;
      }[];
      for (const file of files)
        expect(artifacts[`normalized/${file.id}.md`]).toBeTruthy();
      expect(example.sections.length).toBeGreaterThanOrEqual(2);
      expect(new Set(example.sections.map((s) => s.id)).size).toBe(
        example.sections.length,
      );
    }
  });
});
