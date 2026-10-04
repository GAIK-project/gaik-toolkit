// What the Document → Structured Data demo works with: ready-made documents with the parser
// and the task that suit each, how the options become a request, and how the answer is read.

import { EXAMPLES as EXTRACTOR_EXAMPLES } from "../extractor/extractor-data";
import { EXAMPLES as VISION_EXAMPLES } from "../vision-extractor/vision-data";
import type { ParserType } from "../extractor/extractor-data";

export interface DocumentOptions {
  parser: ParserType;
  generatePdf: boolean;
}

export const DEFAULT_OPTIONS: DocumentOptions = {
  parser: "docling_api",
  generatePdf: false,
};

export interface DocumentExample {
  id: string;
  title: string;
  /** The shape of the result, for the card. */
  shape: string;
  summary: string;
  tags: string[];
  /** The document, a file in public/. */
  url: string;
  fileName: string;
  task: string;
  options: Partial<DocumentOptions>;
  /**
   * The saved schema of this task (a file in api/schemas/). Only the task as written here may
   * use it: once the text is edited, a new schema is made.
   */
  schemaKey: string;
}

// The tasks are the ones the Extractor and the Vision Extractor use for the same documents:
// they were checked there, and one place keeps them in step.
const taskOf = (
  examples: { id: string; task: string }[],
  id: string,
): string => {
  const found = examples.find((example) => example.id === id);
  if (!found) throw new Error(`No example '${id}'`);
  return found.task;
};

export const EXAMPLES: DocumentExample[] = [
  {
    id: "report",
    title: "A business annual report",
    shape: "one record of figures and milestones",
    summary:
      "A report with headings, figures in tables and a list of milestones. The HH Parser turns it into markdown, and the figures are read as numbers.",
    tags: ["PDF", "figures", "HH Parser"],
    url: "/GAIK_Test_Document_Demo.pdf",
    fileName: "GAIK_Test_Document_Demo.pdf",
    schemaKey: "document_structured_report_example",
    task: `Extract the following from the document:
- Document name
- Document number
- Change in annual revenue (percent, as a number)
- Net income
- Active customers
- Customer retention rate (percent, as a number)
- Net promoter score
- Total employees
- Employee satisfaction index
- Key milestones achieved (a list of short phrases)`,
    options: { parser: "docling_api" },
  },
  {
    id: "lease",
    title: "A rental agreement",
    shape: "key terms + a list of charges",
    summary:
      "A text PDF, so the fast local parser is enough: no model call is spent on reading it. The result has the terms of the lease and a list of extra charges.",
    tags: ["PDF", "text layer", "PyMuPDF"],
    url: "/extractor-examples/rental-agreement.pdf",
    fileName: "rental-agreement.pdf",
    schemaKey: "document_structured_lease_example",
    task: taskOf(EXTRACTOR_EXAMPLES, "lease"),
    options: { parser: "pymupdf" },
  },
  {
    id: "receipt",
    title: "A photo of a shop receipt",
    shape: "header + a list of items",
    summary:
      "An image has no text layer, so the Vision parser reads it with a model first. Product names stay as they are printed, in Finnish.",
    tags: ["image", "Finnish", "Vision parser"],
    url: "/vision-extractor-example/receipt.jpg",
    fileName: "receipt.jpg",
    schemaKey: "document_structured_receipt_example",
    task: taskOf(VISION_EXAMPLES, "receipt"),
    options: { parser: "vision" },
  },
  {
    id: "application",
    title: "An employment application form",
    shape: "form + 5 lists",
    summary:
      "A two-page form with typed labels, handwriting and tables. The Vision parser reads it page by page; then the form is turned into one record with lists.",
    tags: ["PDF", "handwriting", "Vision parser"],
    url: "/vision-extractor-example/employment-application.pdf",
    fileName: "employment-application.pdf",
    schemaKey: "document_structured_application_example",
    task: taskOf(VISION_EXAMPLES, "application"),
    options: { parser: "vision" },
  },
];

// ---------------------------------------------------------------------------
// The request
// ---------------------------------------------------------------------------

/** The form fields of a request, as pairs, so that they can be checked without a browser. */
export function formFields(
  options: DocumentOptions,
  task: string,
  schemaKey: string,
  schemaId: string | null = null,
): [string, string][] {
  const fields: [string, string][] = [
    ["user_requirements", task],
    ["parser_type", options.parser],
    ["generate_pdf", String(options.generatePdf)],
    ["pdf_title", "Document Structured Data"],
    // The saved schema is used as it is; a task that was edited gets a new one.
    ["schema_key", schemaKey],
    ["regenerate_schema", "false"],
  ];
  // The schema made in an earlier run of this very task is used again, not made again.
  if (schemaId && !schemaKey) fields.push(["schema_id", schemaId]);
  return fields;
}

// ---------------------------------------------------------------------------
// The answer
// ---------------------------------------------------------------------------

export interface Timings {
  parse_s: number;
  schema_s: number;
  extraction_s: number;
}

/** What took how long, for the line under the result. */
export function timingText(timings: Timings | null | undefined): string {
  if (!timings) return "";
  return [
    `parsing ${timings.parse_s.toFixed(1)} s`,
    `schema ${timings.schema_s.toFixed(1)} s`,
    `extraction ${timings.extraction_s.toFixed(1)} s`,
  ].join(" · ");
}

/** A parser that reads at most 10 pages. */
export const isPageLimited = (parser: ParserType): boolean =>
  parser === "vision" || parser === "vision_plus";

/** The file types of a parser: some read PDFs only. */
export function parserAccepts(parser: ParserType, fileName: string): boolean {
  const ext = fileName.toLowerCase().split(".").pop() ?? "";
  if (parser === "multimodal") return ext === "pdf";
  if (parser === "pymupdf") return ext === "pdf";
  if (parser === "docx") return ext === "docx";
  return true;
}
