// What the Schema Generator demo works with: ready-made tasks, the field builder that
// writes a task for you, and the comparison of two generated schemas.

import type { SchemaField } from "@/components/demo/schema-fields-table";
export type { SchemaField };

// ---------------------------------------------------------------------------
// Ready-made tasks
// ---------------------------------------------------------------------------

/** The three structures the Schema Generator can find. */
export type StructureType = "flat" | "nested_list" | "parent_with_nested_list";

export const STRUCTURE_ORDER: StructureType[] = [
  "flat",
  "nested_list",
  "parent_with_nested_list",
];

export const STRUCTURE_TITLES: Record<StructureType, string> = {
  flat: "Flat",
  nested_list: "Nested list",
  parent_with_nested_list: "Parent with nested list",
};

export interface GalleryTask {
  id: string;
  title: string;
  /** The structure the generator is expected to find for this task. */
  structure: StructureType;
  /** The kinds of field the task asks for, in plain words. */
  types: string[];
  summary: string;
  task: string;
}

// The tasks come from examples/software_components/schema-generator.
export const GALLERY: GalleryTask[] = [
  {
    id: "business-card",
    title: "Business card",
    structure: "flat",
    types: ["text"],
    summary:
      "One person's contact details, with some fields left empty when absent.",
    task: `Extract contact information from a business card. Return the person's full name,
job title, company name, email address, telephone number, website, and postal
address. All fields should be text. The job title, website, and postal address
can be left null if they are not present.
Only fill fields that are explicitly and clearly stated in the text.
Do not guess or infer. If the value of a field is not found, return null.`,
  },
  {
    id: "advisory",
    title: "Security advisory",
    structure: "flat",
    types: ["text", "choice", "number", "date"],
    summary:
      "One advisory with choice fields, a score, a yes or no and a date.",
    task: `Extract the following from the security advisory:
- CVE identifier (e.g. "CVE-2024-12345")
- Affected product
- Affected versions (text string as stated, e.g. "3.2.0 – 3.4.1")
- Severity (Critical, High, Medium, or Low)
- CVSS score (numeric, if stated, else null)
- Attack vector (Network, Adjacent, Local, or Physical)
- Patch available (yes/no)
- Patched version (if stated, else null)
- Published date (Format: DD/MM/YYYY)
- Summary (in a few keywords separated by semicolons)
Only fill fields that are explicitly and clearly stated in the text. Do not guess or infer. If the value of a field is not found, return null.`,
  },
  {
    id: "inventory",
    title: "Inventory items",
    structure: "nested_list",
    types: ["text", "whole number", "decimal number", "choice"],
    summary: "Only a list: one record for every product in the document.",
    task: `Extract every inventory item mentioned in the document and return them as a list.
For each item, return the product name, product code, category, quantity, unit,
unit price, and stock status. Quantity should be an integer and unit price should be
numeric. Stock status must be available, low_stock, out_of_stock, or unknown.
Product code and unit price can be null if they are not present.
Create a separate list entry for every distinct product.`,
  },
  {
    id: "lab-results",
    title: "Laboratory test results",
    structure: "nested_list",
    types: ["text", "number", "choice"],
    summary:
      "Only a list: one record for every test result, with limits and an interpretation.",
    task: `Extract every laboratory test result in the report and return them as a list.
For each result, extract the test name, measured value, unit,
reference-range minimum, reference-range maximum, and interpretation.
The measured value and reference limits should be numeric when possible.
Interpretation must be low, normal, high, abnormal, or unknown.
The unit and reference limits can be null if they are not shown.
Create a separate list entry for every test. Do not provide a medical
interpretation beyond what the report states.`,
  },
  {
    id: "lab-report",
    title: "Laboratory report",
    structure: "parent_with_nested_list",
    types: ["text", "date", "number", "choice"],
    summary: "Patient and report details, plus a list of test results.",
    task: `Extract the patient and report information from a laboratory report.
Return the patient name, patient identifier, date of birth, sample collection date,
report date, laboratory name, and requesting physician.
The requesting physician can be null if not provided.
Also return a list of laboratory test results.
For each result, extract the test name, measured value, unit,
reference-range minimum, reference-range maximum, and interpretation.
The measured value and reference limits should be numeric when possible.
Interpretation must be low, normal, high, abnormal, or unknown.
The unit and reference limits can be null if they are not shown.
Do not provide a medical interpretation beyond what the report states.`,
  },
  {
    id: "meeting-minutes",
    title: "Meeting minutes",
    structure: "parent_with_nested_list",
    types: ["text", "date", "choice"],
    summary: "Meeting details, plus two lists: participants and action items.",
    task: `Extract structured information from meeting minutes. Return the meeting title, date,
start time, end time, location or online platform, chairperson, and summary.
The end time, location or platform, and chairperson can be null.
Return a list of participants containing each participant's name, organization,
and role in the meeting. Also return a separate list of action items. For each
action item, extract the task, responsible person, deadline, priority, and status.
Priority must be low, medium, or high. Status must be not_started, in_progress,
completed, or unknown. The organization, participant role, responsible person,
and deadline can be null.`,
  },
];

// ---------------------------------------------------------------------------
// The field builder
// ---------------------------------------------------------------------------

export const FIELD_TYPES = [
  "text",
  "whole number",
  "number",
  "date",
  "true or false",
  "list of text",
  "choice",
] as const;
export type FieldType = (typeof FIELD_TYPES)[number];

export interface BuilderField {
  id: string;
  name: string;
  type: FieldType;
  description: string;
  required: boolean;
  /** For a choice: the allowed values, separated by commas. */
  choices: string;
}

export type Structure = "single" | "list" | "header-and-list";

export interface BuilderState {
  subject: string;
  structure: Structure;
  fields: BuilderField[];
  /** What the list holds, one entry for each: "line item". */
  listName: string;
  listFields: BuilderField[];
}

export const MAX_BUILDER_FIELDS = 20;

let counter = 0;
export function newField(partial: Partial<BuilderField> = {}): BuilderField {
  counter += 1;
  return {
    id: `f${counter}`,
    name: "",
    type: "text",
    description: "",
    required: false,
    choices: "",
    ...partial,
  };
}

export function initialBuilder(): BuilderState {
  return {
    subject: "a purchase request",
    structure: "single",
    fields: [
      newField({ name: "Requester", description: "Who asked for it" }),
      newField({ name: "Request date", type: "date" }),
      newField({
        name: "Priority",
        type: "choice",
        choices: "low, medium, high",
      }),
      newField({ name: "Estimated cost", type: "number" }),
    ],
    listName: "item",
    listFields: [
      newField({ name: "Item name" }),
      newField({ name: "Quantity", type: "whole number" }),
    ],
  };
}

function fieldLine(field: BuilderField): string | null {
  const name = field.name.trim();
  if (!name) return null;
  const choices = field.choices
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const kind =
    field.type === "choice"
      ? choices.length > 0
        ? `one of: ${choices.join(", ")}`
        : "choice"
      : field.type;
  const description = field.description.trim();
  return `- ${name} (${kind}${field.required ? ", required" : ""})${
    description ? `: ${description}` : ""
  }`;
}

const lines = (fields: BuilderField[]) =>
  fields.map(fieldLine).filter((line): line is string => line !== null);

/** The extraction task that the builder describes. Null while there is nothing to extract. */
export function composeBuilderTask(state: BuilderState): string | null {
  const subject = state.subject.trim() || "the data below";
  const own = lines(state.fields);
  const listLines = lines(state.listFields);
  const listName = state.listName.trim() || "item";
  const closing =
    "Return null for a value that is not stated. Do not infer or invent information.";

  if (state.structure === "single") {
    if (own.length === 0) return null;
    return [
      `Extract ${subject}. It has these fields:`,
      ...own,
      "",
      closing,
    ].join("\n");
  }
  if (state.structure === "list") {
    if (listLines.length === 0) return null;
    return [
      `The text may contain several ${listName} records. Return a list called ${listName}s with one entry for each ${listName}, about ${subject}. Each entry has these fields:`,
      ...listLines,
      "",
      closing,
    ].join("\n");
  }
  if (own.length === 0 && listLines.length === 0) return null;
  return [
    `Extract ${subject}.`,
    "",
    "Header fields:",
    ...own,
    "",
    `Return a list called ${listName}s with one entry for each ${listName}. Each entry has these fields:`,
    ...listLines,
    "",
    closing,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Comparing two schemas
// ---------------------------------------------------------------------------

export interface SchemaChanges {
  added: string[];
  removed: string[];
  changed: { path: string; what: string }[];
}

function flatten(fields: SchemaField[], prefix = ""): Map<string, SchemaField> {
  const out = new Map<string, SchemaField>();
  for (const field of fields) {
    const path = prefix ? `${prefix}.${field.name}` : field.name;
    out.set(path, field);
    if (field.children)
      for (const [childPath, child] of flatten(field.children, path))
        out.set(childPath, child);
  }
  return out;
}

const same = (a?: string[] | null, b?: string[] | null) =>
  (a ?? []).join("|") === (b ?? []).join("|");

/** What differs between two generated schemas, by field path ("lines.price"). */
export function diffFields(
  previous: SchemaField[],
  next: SchemaField[],
): SchemaChanges {
  const before = flatten(previous);
  const after = flatten(next);
  const added = [...after.keys()].filter((path) => !before.has(path));
  const removed = [...before.keys()].filter((path) => !after.has(path));
  const changed: SchemaChanges["changed"] = [];
  for (const [path, field] of after) {
    const old = before.get(path);
    if (!old) continue;
    if (old.type !== field.type)
      changed.push({ path, what: `type ${old.type} → ${field.type}` });
    if (old.required !== field.required)
      changed.push({
        path,
        what: field.required ? "now required" : "now optional",
      });
    if (!same(old.allowed, field.allowed))
      changed.push({
        path,
        what: `allowed values ${(old.allowed ?? []).join(", ") || "none"} → ${
          (field.allowed ?? []).join(", ") || "none"
        }`,
      });
    if (old.description !== field.description)
      changed.push({ path, what: "description changed" });
  }
  return { added, removed, changed };
}

export const hasChanges = (changes: SchemaChanges) =>
  changes.added.length + changes.removed.length + changes.changed.length > 0;

/** Plain words for the structure the generator found. */
export const STRUCTURE_TEXT: Record<string, string> = {
  flat: "One record: one set of fields for each document.",
  nested_list:
    "A list of records: the document holds several records of the same kind.",
  parent_with_nested_list:
    "A header with a list inside: fields for the whole document, plus repeated rows such as line items.",
};
