import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { loadDocument } from "./own-knowledge";
import { rowsToCsv, spreadsheetToCsv } from "./spreadsheet";

describe("rowsToCsv", () => {
  test("quotes cells with commas, quotes and line breaks", () => {
    expect(rowsToCsv([["a,b", 'say "hi"', "x\ny"]])).toBe(
      '"a,b","say ""hi""","x\ny"',
    );
  });

  test("writes empty cells, numbers and dates as plain text", () => {
    const csv = rowsToCsv([
      [null, 12.5, new Date("2026-03-04T00:00:00Z"), true],
    ]);
    expect(csv).toBe(",12.5,2026-03-04,true");
  });

  test("a sheet becomes a catalogue through the CSV reader", () => {
    const csv = rowsToCsv([
      ["Name", "Category", "Price EUR"],
      ["Widget, large", "parts", 12.5],
    ]);
    const doc = loadDocument("list.csv", csv);
    expect(doc.services).toHaveLength(1);
    expect(doc.services[0].name).toBe("Widget, large");
    expect(doc.services[0].category).toBe("parts");
  });
});

// Optional: a real workbook from HELPDESK_DOCS (aurora_price_list.xlsx).
const dir = process.env.HELPDESK_DOCS;
const xlsx = dir ? join(dir, "aurora_price_list.xlsx") : "";
describe.skipIf(!xlsx || !existsSync(xlsx))("real workbook", () => {
  test("reads the filled sheet and leaves the empty one out", async () => {
    const file = new File([readFileSync(xlsx)], "aurora_price_list.xlsx");
    const sheets = await spreadsheetToCsv(file);
    expect(sheets).toHaveLength(1);
    expect(sheets[0].name).toBe("aurora_price_list.csv");
    const doc = loadDocument(sheets[0].name, sheets[0].text);
    expect(doc.services.length).toBeGreaterThanOrEqual(20);
    expect(doc.services.every((s) => /€/.test(s.price))).toBe(true);
  });
});
