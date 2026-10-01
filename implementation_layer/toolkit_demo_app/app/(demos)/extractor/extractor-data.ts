// What the Extractor demo works with: the parsers to choose from, and ready-made
// documents with a matching extraction task.

export type ParserType =
  | "auto"
  | "pymupdf"
  | "docx"
  | "vision"
  | "vision_plus"
  | "docling_api"
  | "multimodal";

export interface ParserOption {
  id: ParserType;
  label: string;
  /** When to choose it. */
  hint: string;
}

// The same parsers, in the same words, as the Parser demo.
export const PARSERS: ParserOption[] = [
  {
    id: "auto",
    label: "Auto-detect",
    hint: "Chooses by file type: PyMuPDF for a PDF, DOCX for a Word file, Vision for an image. A scanned PDF needs another parser.",
  },
  {
    id: "pymupdf",
    label: "PyMuPDF (Fast, text-based)",
    hint: "Fast and local. Reads the text layer of a PDF, so it finds nothing in a scan.",
  },
  {
    id: "docx",
    label: "DOCX (Word documents)",
    hint: "Reads the text and tables of a Word file.",
  },
  {
    id: "vision",
    label: "Vision (AI-powered, handles images)",
    hint: "A vision model reads each page or image. Good for scans and photos. At most 10 pages.",
  },
  {
    id: "vision_plus",
    label: "Vision+ (Text+Image Parsing)",
    hint: "Reads the text and describes the images in the same document. At most 10 pages.",
  },
  {
    id: "docling_api",
    label: "HH Parser (HH's fast Docling Parser)",
    hint: "Haaga-Helia's remote Docling parser: high-quality layout and tables.",
  },
  {
    id: "multimodal",
    label: "Multimodal (Layout-aware, PDF only)",
    hint: "Sends the PDF to the model in one call for layout-aware markdown. PDF only.",
  },
];

export const DEFAULT_PARSER: ParserType = "auto";

/** Files the demo accepts: the same as the Parser demo. */
export const ACCEPTED_FILES =
  ".pdf,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp";

export interface ExtractorExample {
  id: string;
  title: string;
  /** The shape of the result, for the card. */
  shape: string;
  summary: string;
  /** The ready-made document, a file in public/. */
  url: string;
  fileName: string;
  task: string;
}

export const EXAMPLES: ExtractorExample[] = [
  {
    id: "invoice",
    title: "Invoice",
    shape: "header + line items",
    summary: "The amounts of an invoice and every line it bills.",
    url: "/invoice.pdf",
    fileName: "invoice.pdf",
    task: `Extract the invoice details: invoice number, sender name, receiver name, purchase order number, date of invoice, due date, payment terms, currency, subtotal, discount, tax, and grand total.
Also return a list of the invoice lines. For each line, extract the description, quantity, unit, unit price, and line amount.
Amounts and quantities should be numeric. The discount can be null if the invoice has none.`,
  },
  {
    id: "minutes",
    title: "Meeting minutes",
    shape: "header + two lists",
    summary:
      "Meeting details, a list of participants and a list of action items.",
    url: "/extractor-examples/meeting-minutes.pdf",
    fileName: "meeting-minutes.pdf",
    task: `Extract structured information from meeting minutes. Return the meeting title, date, start time, end time, location or online platform, chairperson, and summary.
The end time, location or platform, and chairperson can be null.
Return a list of participants containing each participant's name, organization, and role in the meeting. Also return a separate list of action items. For each action item, extract the task, responsible person, deadline, priority, and status.
Priority must be low, medium, or high. Status must be not_started, in_progress, completed, or unknown. The organization, participant role, responsible person, and deadline can be null.`,
  },
  {
    id: "lab",
    title: "Laboratory report",
    shape: "header + list",
    summary: "Patient and report details, plus a list of test results.",
    url: "/extractor-examples/lab-report.pdf",
    fileName: "lab-report.pdf",
    task: `Extract the patient and report information from a laboratory report.
Return the patient name, patient identifier, date of birth, sample collection date, report date, laboratory name, and requesting physician.
The requesting physician can be null if not provided.
Also return a list of laboratory test results.
For each result, extract the test name, measured value, unit, reference-range minimum, reference-range maximum, and interpretation.
The measured value and reference limits should be numeric when possible.
Interpretation must be low, normal, high, abnormal, or unknown.
The unit and reference limits can be null if they are not shown.
Do not provide a medical interpretation beyond what the report states.`,
  },
  {
    id: "lease",
    title: "Rental agreement",
    shape: "key terms + charges",
    summary:
      "The terms of a lease, with a missing end date, plus a list of extra charges.",
    url: "/extractor-examples/rental-agreement.pdf",
    fileName: "rental-agreement.pdf",
    task: `Extract the key terms of a residential lease agreement. Return the landlord, the tenant, the apartment address, the size in square metres, the lease type (fixed_term or open_ended), the start date, the end date, the monthly rent, the security deposit, the tenant's notice period, whether smoking is allowed, and whether pets are allowed.
The end date should be null for an open-ended lease. Pets are allowed only if the text says so without a condition.
Also return a list of the charges in addition to the rent. For each charge, extract its name, the amount per month, and whether it is included in the rent. The amount can be null if the tenant pays the supplier directly.
Monetary amounts should be numeric, in euros.`,
  },
];

// ---------------------------------------------------------------------------
// Showing a result
// ---------------------------------------------------------------------------

/** Nothing was found: null, an empty text, or an empty list. */
export function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value))
    return value.length === 0 || value.every(isEmptyValue);
  return false;
}

/** How many top-level fields of a record hold a value, and how many there are. */
export function countFound(record: Record<string, unknown>): {
  found: number;
  total: number;
} {
  const values = Object.values(record);
  return {
    found: values.filter((value) => !isEmptyValue(value)).length,
    total: values.length,
  };
}

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** The columns of a list of records, in the order they first appear. */
export function columnsOf(rows: Record<string, unknown>[]): string[] {
  const columns: string[] = [];
  for (const row of rows)
    for (const key of Object.keys(row))
      if (!columns.includes(key)) columns.push(key);
  return columns;
}

/** A value as one line of text, for a table cell. */
export function cellText(value: unknown): string {
  if (isEmptyValue(value)) return "";
  if (Array.isArray(value)) return value.map(cellText).join(", ");
  if (isRecord(value)) return JSON.stringify(value);
  return String(value);
}
