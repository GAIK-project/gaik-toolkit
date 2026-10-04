import { describe, expect, test } from "bun:test";
import {
  HALLUCINATION_EXAMPLES,
  INVOICE_EXAMPLE,
  PAIR_EXAMPLES,
  agreementText,
  applySuggestions,
  fieldRows,
  gridOf,
  majority,
  median,
  meets,
  outcomeOf,
  wordDiff,
  type ValidationFlagLike,
} from "./judge-data";

describe("meets", () => {
  test("ok and wrong are exact; not-ok is anything but ok", () => {
    expect(meets("ok", "ok")).toBe(true);
    expect(meets("ok", "suspect")).toBe(false);
    expect(meets("wrong", "wrong")).toBe(true);
    expect(meets("not-ok", "suspect")).toBe(true);
    expect(meets("not-ok", "wrong")).toBe(true);
    expect(meets("not-ok", "ok")).toBe(false);
  });
});

test("the examples are consistent", () => {
  expect(new Set(PAIR_EXAMPLES.map((e) => e.id)).size).toBe(
    PAIR_EXAMPLES.length,
  );
  for (const example of PAIR_EXAMPLES) {
    expect(example.expected).not.toBe(example.extracted);
  }
  for (const example of HALLUCINATION_EXAMPLES)
    for (const field of example.invented)
      expect(Object.keys(example.extracted)).toContain(field);
  expect(INVOICE_EXAMPLE.extracted).toHaveProperty(INVOICE_EXAMPLE.wrongField);
});

describe("wordDiff", () => {
  test("marks what only one side has", () => {
    const parts = wordDiff(
      "arrived at 14:35 and left",
      "arrived at 14:30 and left",
    );
    expect(parts).toEqual([
      { text: "arrived at", kind: "same" },
      { text: "14:35", kind: "removed" },
      { text: "14:30", kind: "added" },
      { text: "and left", kind: "same" },
    ]);
  });
  test("ignores case, and handles a text that is empty", () => {
    expect(wordDiff("A b", "a B")).toEqual([{ text: "a B", kind: "same" }]);
    expect(wordDiff("", "new words")).toEqual([
      { text: "new words", kind: "added" },
    ]);
  });
});

describe("hallucinations", () => {
  test("outcomeOf compares the flags with what was invented", () => {
    expect(
      outcomeOf(["priority", "location"], ["priority", "follow_up_date"]),
    ).toEqual({
      found: ["priority"],
      missed: ["follow_up_date"],
      extra: ["location"],
    });
  });
  test("fieldRows skips empty fields and gives the judge's word", () => {
    const rows = fieldRows({ a: "x", b: "", c: null, d: 5 }, [
      { field: "d", severity: "wrong", reason: "not in the source" },
    ]);
    expect(rows).toEqual([
      { field: "a", value: "x", status: "supported", reason: null },
      { field: "d", value: "5", status: "wrong", reason: "not in the source" },
    ]);
  });
});

describe("validation", () => {
  const flag: ValidationFlagLike = {
    item_index: 0,
    field: "total",
    severity: "wrong",
    score: 1,
    reason: "subtotal",
    suggested_value: "23 901.62",
  };
  test("gridOf lists the fields of every item with their flag", () => {
    const grid = gridOf([{ total: 20290, vendor: "A" }, { total: 5 }], [flag]);
    expect(grid.map((row) => `${row.item}:${row.field}`)).toEqual([
      "0:total",
      "0:vendor",
      "1:total",
    ]);
    expect(grid[0].flag).toBe(flag);
    expect(grid[1].flag).toBeNull();
  });
  test("an object is one item with the index -1", () => {
    expect(gridOf({ a: 1 }, [])[0].item).toBe(-1);
  });
  test("applySuggestions keeps a number a number, and leaves the original untouched", () => {
    const original = [{ total: 20290, vendor: "A" }];
    const fixed = applySuggestions(original, [flag]) as { total: number }[];
    expect(fixed[0].total).toBe(23901.62);
    expect(original[0].total).toBe(20290);
  });
  test("applySuggestions sets a text and skips a flag with no suggestion", () => {
    const fixed = applySuggestions({ date: "16.3.2026", note: "x" }, [
      { ...flag, item_index: -1, field: "date", suggested_value: "2026-03-16" },
      { ...flag, item_index: -1, field: "note", suggested_value: null },
    ]) as Record<string, string>;
    expect(fixed).toEqual({ date: "2026-03-16", note: "x" });
  });
});

describe("a panel", () => {
  test("majority takes the most common verdict and the harshest on a tie", () => {
    expect(majority(["ok", "ok", "wrong"])).toBe("ok");
    expect(majority(["ok", "wrong"])).toBe("wrong");
    expect(majority([])).toBeNull();
  });
  test("median skips scores of zero", () => {
    expect(median([5, 0, 1, 3])).toBe(3);
    expect(median([])).toBeNull();
  });
  test("agreementText", () => {
    expect(agreementText(1)).toContain("Unanimous");
    expect(agreementText(0.5)).toContain("Mixed");
  });
});
