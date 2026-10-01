import { describe, expect, test } from "bun:test";
import {
  hasContent,
  labelOf,
  severityOf,
  splitAround,
  unwrapRecords,
  valueStrings,
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
