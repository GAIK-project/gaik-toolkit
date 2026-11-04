import { describe, expect, test } from "bun:test";
import {
  hasContent,
  labelOf,
  severityOf,
  splitAround,
  unwrapRecords,
  valueStrings,
  countVerdicts,
  sourceFor,
  type TracedSource,
} from "./format";

test("labelOf makes a readable label", () => {
  expect(labelOf("people_involved")).toBe("People involved");
});

test("hasContent ignores empty values and lists of empty values", () => {
  expect(hasContent("  ")).toBe(false);
  expect(hasContent([null, ""])).toBe(false);
  expect(hasContent(["a"])).toBe(true);
  expect(hasContent(0)).toBe(true);
});

test("valueStrings flattens lists", () => {
  expect(valueStrings(["a", ["b", " "], null])).toEqual(["a", "b"]);
  expect(valueStrings(42)).toEqual(["42"]);
});

describe("splitAround", () => {
  test("finds a value regardless of case", () => {
    expect(splitAround("Slipped on a Wet floor today", "wet floor")).toEqual([
      "Slipped on a ",
      "Wet floor",
      " today",
    ]);
  });
  test("returns null when the value is not quoted", () => {
    expect(splitAround("abc", "xyz")).toBeNull();
    expect(splitAround("abc", "a")).toBeNull();
  });
});

test("severityOf finds the severity word", () => {
  expect(severityOf("Medium")).toBe("medium");
  expect(severityOf("low (minor bruising)")).toBe("low");
  expect(severityOf("unknown")).toBeNull();
});

describe("unwrapRecords", () => {
  test("expands a list of records", () => {
    expect(
      unwrapRecords([{ incidents: [{ date: "a" }, { date: "b" }] }]),
    ).toEqual([{ date: "a" }, { date: "b" }]);
  });
  test("keeps flat items as they are", () => {
    expect(unwrapRecords([{ date: "a", people: ["x"] }])).toEqual([
      { date: "a", people: ["x"] },
    ]);
  });
});

describe("sourceFor", () => {
  const source = (
    field: string,
    value: unknown,
    record: number | null,
    quote = "q",
  ): TracedSource => ({
    field,
    value,
    record,
    quote,
    status: "found",
    span: [0, 1],
  });
  const sources = [
    source("date", "2025-03-15", null, "15.03.2025"),
    source("incidents[0].place", "Depot", 0),
    source("incidents[1].place", "Depot", 1),
    source("incidents[1].people", ["Ann", "Bo"], 1),
  ];

  test("finds the quote of a value worded differently from it", () => {
    expect(sourceFor(sources, "2025-03-15", 1)?.quote).toBe("15.03.2025");
  });

  test("keeps records apart when two have the same value", () => {
    expect(sourceFor(sources, "Depot", 1)?.field).toBe("incidents[1].place");
    expect(sourceFor(sources, "Depot", 0)?.field).toBe("incidents[0].place");
  });

  test("finds one item of a list value, and nothing for an unknown value", () => {
    expect(sourceFor(sources, "Bo", 1)?.field).toBe("incidents[1].people");
    expect(sourceFor(sources, "Bo", 0)).toBeNull();
    expect(sourceFor(undefined, "Bo", 0)).toBeNull();
  });
});

describe("countVerdicts", () => {
  test("counts the verified values and those to check", () => {
    const make = (verdict: TracedSource["verdict"]): TracedSource => ({
      field: "f",
      value: "v",
      record: 0,
      quote: "q",
      status: "found",
      span: [0, 1],
      verdict,
    });
    expect(
      countVerdicts([
        make("verified"),
        make("verified"),
        make("check"),
        make("reworded"),
        make("unchecked"),
      ]),
    ).toEqual({ verified: 2, check: 1 });
    expect(countVerdicts(null)).toEqual({ verified: 0, check: 0 });
  });
});
