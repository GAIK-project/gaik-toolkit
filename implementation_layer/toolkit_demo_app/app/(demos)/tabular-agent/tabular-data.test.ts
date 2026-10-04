import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
  EXAMPLES,
  barsOf,
  columnsOf,
  percent,
  sortRows,
  toCsv,
} from "./tabular-data";

test("every example file exists and has questions", () => {
  expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length);
  for (const example of EXAMPLES) {
    expect(existsSync(`public${example.url}`)).toBe(true);
    expect(example.url.endsWith(example.fileName)).toBe(true);
    expect(example.questions.length).toBeGreaterThanOrEqual(3);
  }
});

describe("sortRows", () => {
  const rows = [
    { n: 10, s: "b" },
    { n: 2, s: "a10" },
    { n: null, s: "a2" },
  ];
  test("numbers sort as numbers, empty values last either way", () => {
    expect(sortRows(rows, "n", false).map((r) => r.n)).toEqual([2, 10, null]);
    expect(sortRows(rows, "n", true).map((r) => r.n)).toEqual([10, 2, null]);
  });
  test("text sorts naturally", () => {
    expect(sortRows(rows, "s", false).map((r) => r.s)).toEqual([
      "a2",
      "a10",
      "b",
    ]);
  });
  test("leaves the input alone", () => {
    sortRows(rows, "n", true);
    expect(rows.map((r) => r.n)).toEqual([10, 2, null]);
  });
});

describe("barsOf", () => {
  test("a label column and a number column become bars", () => {
    expect(
      barsOf([
        { priority: "high", median: 5.65 },
        { priority: "low", median: 30.5 },
      ]),
    ).toEqual({
      labelColumn: "priority",
      valueColumn: "median",
      bars: [
        { label: "high", value: 5.65 },
        { label: "low", value: 30.5 },
      ],
    });
  });
  test("other shapes are not drawn", () => {
    expect(barsOf([{ a: 1 }])).toBeNull();
    expect(
      barsOf([
        { a: "x", b: "y" },
        { a: "z", b: "w" },
      ]),
    ).toBeNull();
    expect(
      barsOf([
        { a: 1, b: 2 },
        { a: 3, b: 4 },
      ]),
    ).toBeNull();
    expect(
      barsOf(Array.from({ length: 30 }, (_, i) => ({ k: `k${i}`, v: i }))),
    ).toBeNull();
  });
});

test("toCsv quotes cells and writes empty values as nothing", () => {
  expect(toCsv([{ a: 'x, "y"', b: null, c: 3 }])).toBe('a,b,c\n"x, ""y""",,3');
  expect(columnsOf([])).toEqual([]);
});

test("percent", () => {
  expect(percent(0.346)).toBe("35%");
});
