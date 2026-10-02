// What the Classifier demo works with: the parsers to choose from, ready-made sets
// of documents with the classes they should get, and how a set of results is read.

export type ClassifierParser = "auto" | "pymupdf" | "docx" | "vision";

export const CLASSIFIER_PARSERS: {
  id: ClassifierParser;
  label: string;
  hint: string;
}[] = [
  {
    id: "auto",
    label: "Auto-detect",
    hint: "This parser is good for any set of files when you are not sure which one to choose: it uses PyMuPDF for a PDF, DOCX for a Word file and Vision for an image.",
  },
  {
    id: "pymupdf",
    label: "PyMuPDF (PDF)",
    hint: "This parser is good for PDFs with a text layer. It is fast and runs locally, and the classifier reads the first 1,000 characters of the text.",
  },
  {
    id: "docx",
    label: "DOCX Parser",
    hint: "This parser is good for Word documents. It reads their text locally, and the classifier reads the first 1,000 characters.",
  },
  {
    id: "vision",
    label: "Vision (images and scans)",
    hint: "This parser is good for photos, images and scanned PDFs, where there is no text layer. A vision model reads the whole page, so it is slower.",
  },
];

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".png", ".jpg", ".jpeg"];
export const MAX_FILES = 10;
export const MAX_FILE_MB = 20;

export interface ExampleDocument {
  url: string;
  /** The class a person would give it: the answer to check the result against. */
  expected: string;
}

export interface ClassifierExample {
  id: string;
  title: string;
  summary: string;
  classes: string[];
  documents: ExampleDocument[];
}

export const fileNameOf = (url: string): string =>
  url.split("/").pop() ?? "document";

const BASE = "/vision-extractor-example";
const EXTRACTOR = "/extractor-examples";
const OWN = "/classifier-examples";

export const EXAMPLES: ClassifierExample[] = [
  {
    id: "business",
    title: "Business documents",
    summary:
      "An invoice, a receipt photo, a lease, a safety report and a cover letter, sorted into five classes.",
    classes: ["invoice", "receipt", "contract", "report", "letter"],
    documents: [
      { url: "/invoice.pdf", expected: "invoice" },
      { url: `${BASE}/receipt.jpg`, expected: "receipt" },
      { url: `${EXTRACTOR}/rental-agreement.pdf`, expected: "contract" },
      { url: `${BASE}/site-safety-inspection.pdf`, expected: "report" },
      { url: `${OWN}/cover-letter.pdf`, expected: "letter" },
    ],
  },
  {
    id: "construction",
    title: "Construction project",
    summary:
      "A drawing, an inspection report, minutes, an invoice and a form, where the classes are close to each other.",
    classes: [
      "drawing",
      "inspection report",
      "meeting minutes",
      "invoice",
      "application form",
      "contract",
    ],
    documents: [
      { url: `${BASE}/blueprint.png`, expected: "drawing" },
      {
        url: `${BASE}/site-safety-inspection.pdf`,
        expected: "inspection report",
      },
      { url: `${EXTRACTOR}/meeting-minutes.pdf`, expected: "meeting minutes" },
      { url: "/invoice.pdf", expected: "invoice" },
      {
        url: `${BASE}/employment-application.pdf`,
        expected: "application form",
      },
    ],
  },
  {
    id: "unknown",
    title: "A document that fits no class",
    summary:
      "Two documents that fit, and two that do not. A document that fits no class gets the automatic class “unknown”.",
    classes: ["invoice", "receipt", "contract"],
    documents: [
      { url: "/invoice.pdf", expected: "invoice" },
      { url: `${BASE}/receipt.jpg`, expected: "receipt" },
      { url: `${OWN}/recipe.pdf`, expected: "unknown" },
      { url: `${EXTRACTOR}/lab-report.pdf`, expected: "unknown" },
    ],
  },
];

// ---------------------------------------------------------------------------
// Reading the results
// ---------------------------------------------------------------------------

export interface Classified {
  filename: string;
  classification: string;
  confidence: number;
  reasoning: string;
}

/** How many documents each class got, the largest first. */
export function countByClass(results: Classified[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const result of results)
    counts.set(
      result.classification,
      (counts.get(result.classification) ?? 0) + 1,
    );
  return [...counts.entries()].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
}

/** How many results agree with the expected class, among those that have one. */
export function agreement(
  results: Classified[],
  expected: Record<string, string>,
): { matching: number; checked: number } {
  let matching = 0;
  let checked = 0;
  for (const result of results) {
    const answer = expected[result.filename];
    if (answer === undefined) continue;
    checked += 1;
    if (answer.toLowerCase() === result.classification.toLowerCase())
      matching += 1;
  }
  return { matching, checked };
}

const csvCell = (value: string | number): string => {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export function toCsv(results: Classified[]): string {
  const rows = results.map((result) =>
    [
      result.filename,
      result.classification,
      result.confidence.toFixed(2),
      result.reasoning,
    ]
      .map(csvCell)
      .join(","),
  );
  return ["filename,class,confidence,reasoning", ...rows].join("\n");
}

/** The class names from a text: trimmed, lower case, without repeats or blanks. */
export function parseClasses(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(/[,\n]/)) {
    const name = part.trim().toLowerCase();
    if (name) seen.add(name);
  }
  return [...seen];
}
