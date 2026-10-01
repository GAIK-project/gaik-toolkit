// The built-in example of the Purchase Order demo: the documents in
// public/data/po-bom-example, what is read from each and how the order is priced.

export const EXAMPLE_DIR = "/data/po-bom-example";
/** The purchase order of the single-file example, which has its own document. */
export const SINGLE_EXAMPLE_DIR = "/data/po-single-example";

export type DocumentKind = "po" | "bom" | "price";

export interface ExtractedField {
  name: string;
  note?: string;
}

export interface FieldGroup {
  title: string;
  fields: ExtractedField[];
}

export interface ExampleDocument {
  file: string;
  kind: DocumentKind;
  title: string;
  summary: string;
  /** How the fields are read: by the model, or straight from the sheet. */
  method: "ai" | "sheet";
  fields: ExtractedField[];
  /** Fields in titled groups, for documents whose fields are not one flat list. */
  groups?: FieldGroup[];
}

/** The two examples: a PO alone, or a PO with its BOMs and a price list. */
export type ExampleCase = "single" | "multi";

// Keep the fields in step with POItem, PurchaseOrder, BOMData and PricingRow in
// api/routers/luvata_order.py.
const BOM_FIELDS: ExtractedField[] = [
  { name: "Material ID" },
  { name: "Type designation" },
  { name: "Dimensions" },
  { name: "Material grade" },
  { name: "Cutting required", note: "yes / no" },
  { name: "Testing required", note: "yes / no" },
  { name: "Certificates required", note: "yes / no" },
];

export const EXAMPLE_DOCUMENTS: ExampleDocument[] = [
  {
    file: "PO.pdf",
    kind: "po",
    title: "Purchase order",
    summary:
      "AutoTech Manufacturing Corp. orders three materials from Precision Steel & Components. " +
      "The aim is to extract all the top-level header fields (PO number, customer, order date, buyer, " +
      "sales person, shipping address, payment terms, shipping cost and tax rate) and, for each line " +
      "item, the quantity, the unit price, the details from its BOM and the additional fees that " +
      "apply (such as cutting, certificates, hydrostatic testing and packaging). The total price is " +
      "then calculated with a breakdown: material subtotal, additional fees, shipping, tax and grand " +
      "total. The total printed on the purchase order does not include these additional fees.",
    method: "ai",
    fields: [
      { name: "PO number" },
      { name: "Customer" },
      { name: "Customer address", note: "if present" },
      { name: "Delivery address", note: "if present" },
      { name: "Invoicing address", note: "if present" },
      { name: "Line items", note: "material, description, quantity" },
      { name: "Delivery date", note: "per line, if present" },
    ],
  },
  {
    file: "BOM1.pdf",
    kind: "bom",
    title: "Bill of materials 1",
    summary: "Technical details of the aluminum angle, MAT-2401.",
    method: "ai",
    fields: BOM_FIELDS,
  },
  {
    file: "BOM2.pdf",
    kind: "bom",
    title: "Bill of materials 2",
    summary: "Technical details of the stainless steel sheet, MAT-3567.",
    method: "ai",
    fields: BOM_FIELDS,
  },
  {
    file: "BOM3.pdf",
    kind: "bom",
    title: "Bill of materials 3",
    summary: "Technical details of the seamless carbon steel pipe, MAT-4829.",
    method: "ai",
    fields: BOM_FIELDS,
  },
  {
    file: "price list.xlsx",
    kind: "price",
    title: "Master price list",
    summary:
      "The supplier's unit prices and cutting, testing and certificate fees for 20 materials.",
    method: "sheet",
    fields: [
      { name: "Material ID / type designation" },
      { name: "Unit price" },
      { name: "Cutting fee" },
      { name: "Testing fee" },
      { name: "Certificate fee" },
    ],
  },
];

/** The BOM that describes each material of the example order. */
export const BOM_OF_MATERIAL: Record<string, string> = {
  "MAT-2401": "BOM1.pdf",
  "MAT-3567": "BOM2.pdf",
  "MAT-4829": "BOM3.pdf",
};

/** The steps of processing, in order; `match` picks the step from a status message. */
export const PROCESS_STEPS: { label: string; match: RegExp }[] = [
  { label: "Parsing documents", match: /parsing/i },
  { label: "Extracting information", match: /extracting/i },
  { label: "Preparing results", match: /preparing/i },
];

/** The index of the processing step a status message belongs to, or -1. */
export function stepOfStatus(message: string): number {
  return PROCESS_STEPS.findIndex((step) => step.match.test(message));
}

// --- The single-file example: the purchase order alone ---------------------------
// The fields follow the starting prompt of "Single-file purchase order" in
// prompt-template.ts, which is also what the example is processed with.

export const SINGLE_EXAMPLE_DOCUMENTS: ExampleDocument[] = [
  {
    file: "PO.pdf",
    kind: "po",
    title: "Purchase order",
    summary:
      "Kestilä Industrial Systems Oy orders three materials from Baltic Metals Trading GmbH. " +
      "The aim is to extract the top-level header fields (order date, delivery date, order number, " +
      "supplier number and shipping address) and the information of each line item (item number, " +
      "description, quantity, unit price and material number). The total on the order does not " +
      "include the additional fees listed under each position, so this example only extracts " +
      "what the order states; it does not price the fees or calculate a new total.",
    method: "ai",
    fields: [],
    groups: [
      {
        title: "Top-level fields",
        fields: [
          { name: "Purchase order date", note: "DD/MM/YYYY" },
          { name: "Delivery date", note: "DD/MM/YYYY" },
          { name: "Purchase order number", note: "dash after every 4 digits" },
          { name: "Supplier number" },
          {
            name: "Shipping address",
            note: "company, street, postal code, city, country",
          },
        ],
      },
      {
        title: "For each line item",
        fields: [
          { name: "Item number", note: "e.g. 010, 020" },
          {
            name: "Description",
            note: "the item's name, not its specification",
          },
          { name: "Quantity", note: "with its unit" },
          { name: "Price per currency" },
          { name: "Material number" },
        ],
      },
    ],
  },
];

/** What each case is, for the selector. */
export const EXAMPLE_CASES: {
  value: ExampleCase;
  title: string;
  description: string;
}[] = [
  {
    value: "single",
    title: "Single-file purchase order (extraction only)",
    description: "One PO PDF, read into header fields and line items.",
  },
  {
    value: "multi",
    title:
      "Purchase order + BOMs + price list (Extraction and order draft generation)",
    description:
      "A PO, its bills of materials and a price list, turned into a priced order.",
  },
];

/** The steps of the single-file example: one request each. */
export const SINGLE_PROCESS_STEPS = [
  "Preparing the extraction schema",
  "Reading the document and extracting information",
];
