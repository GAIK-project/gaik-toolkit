import { describe, expect, it } from "vitest";
import { formatValue as shownValue } from "./case-value";
import {
  NO_RUN_OUTPUT,
  documentSections,
  fieldLabel,
  formatSize,
  formatValue,
  hasRunOutput,
  isConfidenceField,
  isReviewFlagField,
  outputFileEntries,
  recordTable,
  pocRunOutput,
  nestedNumber,
  recordRows,
  restoredRun,
  runEndMessage,
  runFileHref,
  valueText,
} from "./poc-run-output";

// The PoC tab showed a finished run as its raw log, with the result somewhere
// in it. These pin how the api's reading of the output block is taken in and
// turned into something a person reads.

describe("pocRunOutput", () => {
  it("is empty for nothing, garbage and a run that wrote no files", () => {
    expect(pocRunOutput(null)).toEqual(NO_RUN_OUTPUT);
    expect(pocRunOutput("x")).toEqual(NO_RUN_OUTPUT);
    const none = pocRunOutput({ run_id: "r1", record: null, files: [] });
    expect(none.runId).toBe("r1");
    expect(hasRunOutput(none)).toBe(false);
  });

  it("keeps the record, the check, the texts and the files the api read", () => {
    const o = pocRunOutput({
      run_id: "r1",
      record: { location: "Hall 3", urgency: "high" },
      validation: { passed: false, issues: ["x"] },
      transcript: "said this",
      document: "# Summary",
      files: [
        { name: "ticket.json", body: "{}" },
        { name: "bad", body: 3 },
        "not a file",
      ],
    });
    expect(o.record).toEqual({ location: "Hall 3", urgency: "high" });
    expect(o.validation?.passed).toBe(false);
    expect(o.transcript).toBe("said this");
    expect(o.document).toBe("# Summary");
    expect(o.files).toEqual([{ name: "ticket.json", body: "{}" }]);
    expect(hasRunOutput(o)).toBe(true);
  });

  it("takes several records as a list and drops a record that is not an object", () => {
    expect(pocRunOutput({ record: [{ a: 1 }, { a: 2 }], files: [] }).record).toEqual([{ a: 1 }, { a: 2 }]);
    expect(pocRunOutput({ record: "text", files: [] }).record).toBeNull();
    expect(pocRunOutput({ record: [{ a: 1 }, "x"], files: [] }).record).toBeNull();
  });
});

describe("the record as rows", () => {
  it("labels the fields and writes the values as text", () => {
    expect(fieldLabel("incident_location")).toBe("Incident location");
    expect(fieldLabel("dueDate")).toBe("Due date");
    expect(valueText(null)).toBe("");
    expect(valueText(3)).toBe("3");
    expect(valueText(["a", "b"])).toBe("a, b");
    expect(valueText({ k: 1 })).toBe('{\n  "k": 1\n}');
    expect(recordRows({ po_number: "PO-1", lines: [{ n: 1 }] })).toEqual([
      { field: "po_number", label: "Po number", value: "PO-1" },
      {
        field: "lines",
        label: "Lines",
        value: '[\n  {\n    "n": 1\n  }\n]',
      },
    ]);
  });

  it("says a nested confidence on the 0-1 scale as a percentage, and no other number", () => {
    expect(nestedNumber("confidence", 0.93, FI_WORDS, [{ confidence: 0.93 }])).toBe("93 %");
    expect(nestedNumber("confidence", 87, FI_WORDS, [{ confidence: 87 }])).toBeUndefined();
    expect(nestedNumber("quantity", 0.5, FI_WORDS, [{ quantity: 0.5 }])).toBeUndefined();
  });

  it("says a nested bare 0 or 1 confidence as a percentage only beside a fraction, as recordRows does", () => {
    // 1 on a 1-5 scale must not read "100 %".
    expect(nestedNumber("confidence", 1, FI_WORDS, [{ confidence: 1 }])).toBeUndefined();
    expect(nestedNumber("confidence", 0, FI_WORDS, [{ confidence: 0 }])).toBeUndefined();
    expect(nestedNumber("confidence", 1, FI_WORDS, [{ confidence: 1, match_probability: 0.4 }])).toBe("100 %");
  });

  it("reads a nested list of confidences 4 and 1 as written, and 0.5 and 1 as percentages", () => {
    const words = {
      yes: "Kyllä",
      no: "Ei",
      number: (field: string, n: number, among: Record<string, unknown>[]) => nestedNumber(field, n, FI_WORDS, among),
    };
    const cells = (value: unknown) => {
      const shown = shownValue(value, words);
      return shown.kind === "records" ? shown.rows.map((row) => row[0].value) : shown;
    };
    expect(cells([{ confidence: 4 }, { confidence: 1 }])).toEqual([
      { kind: "text", text: "4" },
      { kind: "text", text: "1" },
    ]);
    expect(cells([{ confidence: 0.5 }, { confidence: 1 }])).toEqual([
      { kind: "text", text: "50 %" },
      { kind: "text", text: "100 %" },
    ]);
    // One object nested in the record: its own confidences decide.
    expect(shownValue({ score: { confidence: 1 } }, words)).toEqual({
      kind: "pairs",
      pairs: [{ label: "Score", value: { kind: "pairs", pairs: [{ label: "Confidence", value: { kind: "text", text: "1" } }] } }],
    });
  });

  it("reads a document result as sections, and an ordinary record as none", () => {
    expect(documentSections({ sections: [{ title: "A", text: "one" }, { text: "two" }] })).toEqual([
      { title: "A", text: "one" },
      { title: "2", text: "two" },
    ]);
    expect(documentSections({ location: "Hall 3" })).toBeNull();
    expect(documentSections({ sections: [] })).toBeNull();
  });
});

describe("runEndMessage", () => {
  it("prefers the reason read from the log over the Job's own words", () => {
    expect(
      runEndMessage({ phase: "failed", reason: "KeyError: 'x.pdf'", message: "backoff limit" }),
    ).toBe("KeyError: 'x.pdf'");
    expect(runEndMessage({ phase: "failed", message: "backoff limit" })).toBe("backoff limit");
    expect(runEndMessage({ phase: "timeout", reason: "the run passed its ten-minute limit" })).toBe(
      "the run passed its ten-minute limit",
    );
    expect(runEndMessage({ phase: "failed", reason: "  ", message: "" })).toBeNull();
  });

  it("keeps the Job's message for a run that succeeded", () => {
    expect(runEndMessage({ phase: "succeeded", reason: "stale", message: null })).toBeNull();
  });
});

describe("run downloads", () => {
  it("reads the files the run printed for download and the skipped ones", () => {
    const out = pocRunOutput({
      run_id: "r1",
      files: [],
      downloads: [{ name: "report.pdf", size: 2048 }, { name: 3, size: 1 }],
      skipped: [{ name: "huge.bin", size: 9_000_000 }],
    });
    expect(out.downloads).toEqual([{ name: "report.pdf", size: 2048 }]);
    expect(out.skipped).toEqual([{ name: "huge.bin", size: 9_000_000 }]);
    // A run that produced only a PDF still has output.
    expect(hasRunOutput(out)).toBe(true);
  });

  it("has none when the api answers without them", () => {
    const out = pocRunOutput({ run_id: "r1", files: [] });
    expect(out.downloads).toEqual([]);
    expect(out.skipped).toEqual([]);
    expect(hasRunOutput(out)).toBe(false);
  });

  it("links each file through the session's own route", () => {
    expect(runFileHref("s 1", "run-1", "raportti ä.pdf")).toBe(
      "/api/sessions/s%201/runs/run-1/files/raportti%20%C3%A4.pdf",
    );
  });

  it("shows sizes for people", () => {
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(2048)).toBe("2 kB");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("restoredRun", () => {
  it("shows a finished run again with its outcome", () => {
    expect(
      restoredRun({ run_id: "r1", phase: "succeeded", exit_code: 0, message: null, finished: true }),
    ).toEqual({ phase: "succeeded", message: null, finished: true });
  });

  it("says why a failed run failed, from the reason read from its log", () => {
    expect(
      restoredRun({
        phase: "failed",
        exit_code: 1,
        message: "BackoffLimitExceeded",
        reason: "ERROR: no input with ['.wav'] under /workspace/poc/sample_input",
        finished: true,
      }),
    ).toEqual({
      phase: "failed",
      message: "ERROR: no input with ['.wav'] under /workspace/poc/sample_input",
      finished: true,
    });
    expect(restoredRun({ phase: "timeout", message: "deadline", finished: true })).toEqual({
      phase: "timeout",
      message: "deadline",
      finished: true,
    });
  });

  it("follows a run that is still going", () => {
    for (const phase of ["pending", "running"]) {
      expect(restoredRun({ phase, finished: false })).toEqual({
        phase: "running",
        message: null,
        finished: false,
      });
    }
  });

  it("leaves the tab alone for an answer it cannot use", () => {
    expect(restoredRun(null)).toBeNull();
    expect(restoredRun("x")).toBeNull();
    expect(restoredRun({ phase: "unknown", finished: true })).toBeNull();
    expect(restoredRun({ phase: "running", finished: true })).toBeNull();
  });
});

const FI_WORDS = { yes: "Kyllä", no: "Ei", percent: "{n} %" };

describe("values as the result shows them", () => {
  it("writes booleans as yes and no", () => {
    expect(formatValue("paid", true, FI_WORDS)).toBe("Kyllä");
    expect(formatValue("paid", false, FI_WORDS)).toBe("Ei");
  });

  it("writes a 0-1 confidence as a percentage, and leaves other numbers alone", () => {
    expect(formatValue("confidence", 0.93, FI_WORDS)).toBe("93 %");
    expect(formatValue("classificationConfidence", 1, FI_WORDS)).toBe("100 %");
    expect(formatValue("conf", 0.5, FI_WORDS)).toBe("50 %");
    expect(formatValue("confidence", 7, FI_WORDS)).toBe("7");
    expect(formatValue("total", 0.93, FI_WORDS)).toBe("0.93");
  });

  it("keeps the raw text without words", () => {
    expect(formatValue("paid", true)).toBe("true");
    expect(formatValue("confidence", 0.93)).toBe("0.93");
  });

  it("knows confidence and review-flag fields by name", () => {
    for (const f of ["confidence", "certainty", "match_probability", "conf"]) {
      expect(isConfidenceField(f)).toBe(true);
    }
    for (const f of ["config", "conference_room", "total"]) expect(isConfidenceField(f)).toBe(false);
    for (const f of ["needs_review", "needsReview", "requires_human_review", "review_required", "manual_review", "flagged"]) {
      expect(isReviewFlagField(f)).toBe(true);
    }
    for (const f of ["reviewer", "review_notes", "status"]) expect(isReviewFlagField(f)).toBe(false);
    // True here means the record passed, not that it needs a person.
    for (const f of ["verification", "check", "review", "verified"]) expect(isReviewFlagField(f)).toBe(false);
  });
});

describe("recordTable", () => {
  const invoices = [
    { supplier: "Lyreco Finland Oy", total: "412.90 EUR", confidence: 0.93, paid: true, needs_review: false },
    { supplier: "Elisa Oyj", total: "1 280.00 EUR", confidence: 0.71, paid: false, needs_review: true },
  ];

  it("puts two or more flat records in one table, a row each", () => {
    const table = recordTable(invoices, FI_WORDS);
    expect(table?.columns.map((c) => c.label)).toEqual(["Supplier", "Total", "Confidence", "Paid"]);
    expect(table?.rows).toEqual([
      { cells: ["Lyreco Finland Oy", "412.90 EUR", "93 %", "Kyllä"], flagged: false },
      { cells: ["Elisa Oyj", "1 280.00 EUR", "71 %", "Ei"], flagged: true },
    ]);
  });

  it("takes the columns in the order the fields first appear, blank where a record lacks one", () => {
    const table = recordTable([{ a: 1 }, { b: "x", a: 2 }], FI_WORDS);
    expect(table?.columns.map((c) => c.field)).toEqual(["a", "b"]);
    expect(table?.rows.map((r) => r.cells)).toEqual([
      ["1", ""],
      ["2", "x"],
    ]);
  });

  it("a single record's bare 0 or 1 confidence is a percentage only beside a fraction", () => {
    const value = (record: Record<string, unknown>, field: string) =>
      recordRows(record, FI_WORDS).find((r) => r.field === field)?.value;
    // 1 on a 1-5 scale must not read "100 %".
    expect(value({ confidence: 1 }, "confidence")).toBe("1");
    expect(value({ confidence: 0 }, "confidence")).toBe("0");
    expect(value({ confidence: 0.93 }, "confidence")).toBe("93 %");
    expect(value({ confidence: 1, match_probability: 0.4 }, "confidence")).toBe("100 %");
    expect(value({ confidence: 4 }, "confidence")).toBe("4");
  });

  it("shows a confidence column as percentages only when every value is on the 0-1 scale", () => {
    const table = recordTable([{ id: 1, confidence: 87 }, { id: 2, confidence: 1 }], FI_WORDS);
    expect(table?.rows.map((r) => r.cells[1])).toEqual(["87", "1"]);
  });

  it("keeps a column of bare 0s and 1s as written, with no fraction to give the scale", () => {
    const bare = recordTable([{ id: 1, confidence: 1 }, { id: 2, confidence: 0 }], FI_WORDS);
    expect(bare?.rows.map((r) => r.cells[1])).toEqual(["1", "0"]);
    const mixed = recordTable([{ id: 1, confidence: 1 }, { id: 2, confidence: 0.6 }], FI_WORDS);
    expect(mixed?.rows.map((r) => r.cells[1])).toEqual(["100 %", "60 %"]);
  });

  it("keeps a passed verification as a column instead of marking every row", () => {
    const table = recordTable([{ id: 1, verification: true }, { id: 2, verification: true }], FI_WORDS);
    expect(table?.columns.map((c) => c.field)).toEqual(["id", "verification"]);
    expect(table?.rows.every((r) => !r.flagged)).toBe(true);
  });

  it("keeps a review field that holds text as a column", () => {
    const table = recordTable([{ id: 1, review: "ok" }, { id: 2, review: "check total" }], FI_WORDS);
    expect(table?.columns.map((c) => c.field)).toEqual(["id", "review"]);
    expect(table?.rows.every((r) => !r.flagged)).toBe(true);
  });

  it("is no table for one record, nested values or document sections", () => {
    expect(recordTable([invoices[0]], FI_WORDS)).toBeNull();
    expect(recordTable([{ a: 1, lines: [{ x: 1 }] }, { a: 2, lines: [] }], FI_WORDS)).toBeNull();
    expect(recordTable([{ a: { b: 1 } }, { a: { b: 2 } }], FI_WORDS)).toBeNull();
    expect(recordTable([{ sections: [{ title: "A", text: "x" }] }, { sections: [] }], FI_WORDS)).toBeNull();
  });

  it("is no table when the flag is the only field", () => {
    expect(recordTable([{ needs_review: true }, { needs_review: false }], FI_WORDS)).toBeNull();
  });
});

describe("outputFileEntries", () => {
  it("lists each file once, with its download and its text", () => {
    const o = pocRunOutput({
      run_id: "r1",
      files: [
        { name: "result.json", body: "[]" },
        { name: "notes.txt", body: "hello" },
      ],
      downloads: [
        { name: "result.json", size: 2048 },
        { name: "report.pdf", size: 9000 },
      ],
    });
    expect(outputFileEntries(o)).toEqual([
      { name: "result.json", size: 2048, body: "[]", downloadable: true },
      { name: "report.pdf", size: 9000, body: null, downloadable: true },
      { name: "notes.txt", size: null, body: "hello", downloadable: false },
    ]);
  });

  it("offers no download without a run id", () => {
    const o = pocRunOutput({ files: [{ name: "a.txt", body: "x" }], downloads: [{ name: "b.pdf", size: 1 }] });
    expect(outputFileEntries(o)).toEqual([{ name: "a.txt", size: null, body: "x", downloadable: false }]);
  });
});
