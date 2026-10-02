import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
  EXAMPLES,
  countMatches,
  outlineOf,
  parseBlocks,
  parseInline,
  splitByQuery,
  statsOf,
  toPlainText,
} from "./parser-data";

const DOC = `# Title

Some **bold** and *italic* text with \`code\`.

## Items

- one
- two
  - nested

| Name | Qty |
| --- | --- |
| Pen | 2 |
| Ink | 5 |

> quoted

\`\`\`
raw | text
\`\`\`
`;

describe("parseBlocks", () => {
  const blocks = parseBlocks(DOC);
  test("finds headings, a list, a table, a quote and code", () => {
    expect(blocks.map((b) => b.type)).toEqual([
      "heading",
      "paragraph",
      "heading",
      "list",
      "table",
      "quote",
      "code",
    ]);
  });
  test("reads a table as a header and rows", () => {
    const table = blocks.find((b) => b.type === "table");
    expect(table).toEqual({
      type: "table",
      header: ["Name", "Qty"],
      rows: [
        ["Pen", "2"],
        ["Ink", "5"],
      ],
    });
  });
  test("keeps the depth of nested list items", () => {
    const list = blocks.find((b) => b.type === "list");
    expect(
      list && list.type === "list" && list.items.map((i) => i.depth),
    ).toEqual([0, 0, 1]);
  });
  test("a pipe inside code is not a table", () => {
    expect(blocks.filter((b) => b.type === "table")).toHaveLength(1);
  });
  test("skips html comments such as image markers", () => {
    expect(parseBlocks("<!-- image -->\n\ntext").map((b) => b.type)).toEqual([
      "paragraph",
    ]);
  });
});

test("parseInline reads bold, italic, code and links", () => {
  expect(parseInline("a **b** *c* `d` [e](http://x)").map((p) => p.t)).toEqual([
    "text",
    "bold",
    "text",
    "italic",
    "text",
    "code",
    "text",
    "link",
  ]);
  expect(parseInline("![chart](x.png)")).toEqual([
    { t: "text", text: "chart" },
  ]);
});

test("outline and statistics of a document", () => {
  const blocks = parseBlocks(DOC);
  expect(outlineOf(blocks)).toEqual([
    { id: "md-h-0", level: 1, text: "Title" },
    { id: "md-h-1", level: 2, text: "Items" },
  ]);
  const stats = statsOf(DOC, blocks);
  expect(stats.headings).toBe(2);
  expect(stats.tables).toBe(1);
  expect(stats.lists).toBe(1);
  expect(stats.words).toBeGreaterThan(10);
});

test("toPlainText drops the marks and keeps the words", () => {
  const plain = toPlainText(DOC);
  expect(plain).toContain("Some bold and italic text with code.");
  expect(plain).toContain("Pen\t2");
  expect(plain).not.toContain("**");
});

describe("search", () => {
  test("counts matches without caring about case", () => {
    expect(countMatches("Pen pen PEN", "pen")).toBe(3);
    expect(countMatches("anything", "  ")).toBe(0);
  });
  test("splits at the matches and escapes the query", () => {
    expect(splitByQuery("a.b A.B", "a.b")).toEqual([
      { text: "a.b", hit: true },
      { text: " ", hit: false },
      { text: "A.B", hit: true },
    ]);
  });
});

test("every example file exists in public/", () => {
  for (const example of EXAMPLES)
    expect(existsSync(`public${example.url}`)).toBe(true);
});
