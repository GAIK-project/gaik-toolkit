import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
  ACCEPTED_EXTENSIONS,
  EXAMPLES,
  agreement,
  countByClass,
  fileNameOf,
  parseClasses,
  toCsv,
  type Classified,
} from "./classifier-data";

const result = (
  filename: string,
  classification: string,
  confidence = 0.9,
): Classified => ({
  filename,
  classification,
  confidence,
  reasoning: "because",
});

describe("the examples", () => {
  test("every file exists and has an accepted type", () => {
    for (const example of EXAMPLES)
      for (const document of example.documents) {
        expect(existsSync(`public${document.url}`)).toBe(true);
        expect(ACCEPTED_EXTENSIONS).toContain(
          `.${fileNameOf(document.url).split(".").pop()}`,
        );
      }
  });
  test("every expected class is one of the classes, or unknown", () => {
    for (const example of EXAMPLES)
      for (const document of example.documents)
        expect([...example.classes, "unknown"]).toContain(document.expected);
  });
  test("one set has documents that fit no class", () => {
    const unknown = EXAMPLES.find((e) => e.id === "unknown");
    expect(unknown?.documents.some((d) => d.expected === "unknown")).toBe(true);
  });
  test("file names are unique within a set", () => {
    for (const example of EXAMPLES) {
      const names = example.documents.map((d) => fileNameOf(d.url));
      expect(new Set(names).size).toBe(names.length);
    }
  });
});

test("countByClass counts and sorts", () => {
  expect(
    countByClass([
      result("a", "invoice"),
      result("b", "letter"),
      result("c", "invoice"),
    ]),
  ).toEqual([
    ["invoice", 2],
    ["letter", 1],
  ]);
});

test("agreement compares with the expected class, ignoring case", () => {
  const results = [
    result("a", "Invoice"),
    result("b", "letter"),
    result("c", "x"),
  ];
  expect(agreement(results, { a: "invoice", b: "report" })).toEqual({
    matching: 1,
    checked: 2,
  });
});

test("toCsv quotes cells with commas and quotes", () => {
  const csv = toCsv([
    { ...result("a b.pdf", "invoice"), reasoning: 'has "a, b"' },
  ]);
  expect(csv).toBe(
    'filename,class,confidence,reasoning\na b.pdf,invoice,0.90,"has ""a, b"""',
  );
});

test("parseClasses trims, lowercases and drops repeats", () => {
  expect(parseClasses("Invoice, receipt\n invoice ,,Letter")).toEqual([
    "invoice",
    "receipt",
    "letter",
  ]);
});
