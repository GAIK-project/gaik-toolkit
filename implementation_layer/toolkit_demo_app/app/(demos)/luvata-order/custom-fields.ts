// The fields offered in "Create your use case". The description is sent with the field
// name, so the schema generator knows what each one means.

import type { UseCaseMode } from "./prompt-template";

export interface FieldChoice {
  label: string;
  description: string;
  /** Ticked when the section opens: what the standard flow already extracts. */
  defaultOn?: boolean;
}

export interface CustomField {
  name: string;
  description: string;
}

export type FieldGroupKey = "header" | "lineItems" | "bom";

export const FIELD_GROUPS: Record<
  FieldGroupKey,
  { title: string; hint: string; choices: FieldChoice[] }
> = {
  header: {
    title: "Purchase order: header fields",
    hint: "Stated once per order.",
    choices: [
      {
        label: "PO number",
        description: "Purchase order number",
        defaultOn: true,
      },
      {
        label: "Customer name",
        description: "Customer or buyer name",
        defaultOn: true,
      },
      { label: "Order date", description: "Date the order was placed" },
      { label: "Supplier name", description: "Supplier or vendor name" },
      { label: "Supplier number", description: "Supplier or vendor number" },
      { label: "Buyer", description: "Person or company placing the order" },
      { label: "Sales person", description: "Sales person named on the order" },
      { label: "Customer address", description: "Customer or buyer address" },
      { label: "Delivery address", description: "Address to deliver to" },
      { label: "Invoicing address", description: "Address to invoice" },
      { label: "Currency", description: "Currency of the prices" },
      { label: "Payment terms", description: "Payment terms or due days" },
      {
        label: "Delivery terms",
        description: "Delivery terms, such as Incoterms",
      },
      { label: "Contact person", description: "Buyer's contact person" },
      { label: "Total amount", description: "Total value of the order" },
    ],
  },
  lineItems: {
    title: "Purchase order: line items",
    hint: "Repeated for every order line.",
    choices: [
      {
        label: "Material number",
        description: "Material number or code of the line",
        defaultOn: true,
      },
      {
        label: "Description",
        description: "Item description",
        defaultOn: true,
      },
      {
        label: "Quantity",
        description: "Ordered quantity as a number",
        defaultOn: true,
      },
      {
        label: "Delivery date",
        description: "Requested delivery date of the line",
        defaultOn: true,
      },
      {
        label: "Item number",
        description: "Position of the line, e.g. 010, 020",
      },
      { label: "Unit", description: "Unit of measure, such as pcs or kg" },
      { label: "Unit price", description: "Price per unit" },
      { label: "Line total", description: "Total price of the line" },
    ],
  },
  bom: {
    title: "Bills of materials",
    hint: "Stated once per BOM.",
    choices: [
      {
        label: "Material ID",
        description: "Material ID, for example MAT-2401",
        defaultOn: true,
      },
      {
        label: "Type designation",
        description: "Product type designation",
        defaultOn: true,
      },
      {
        label: "Dimensions",
        description: "Product dimensions",
        defaultOn: true,
      },
      {
        label: "Material grade",
        description: "Material grade or standard",
        defaultOn: true,
      },
      {
        label: "Cutting required",
        description: "Whether a cutting service is required (true or false)",
      },
      {
        label: "Testing required",
        description: "Whether testing is required (true or false)",
      },
      {
        label: "Certificates required",
        description: "Whether certificates are required (true or false)",
      },
      { label: "Weight", description: "Weight of the product" },
      { label: "Supplier", description: "Supplier or manufacturer name" },
    ],
  },
};

export const MAX_CUSTOM_FIELDS = 30;
export const MAX_BOMS = 10;

/** The fields ticked by default for one group. */
export function defaultSelection(group: FieldGroupKey): string[] {
  return FIELD_GROUPS[group].choices
    .filter((choice) => choice.defaultOn)
    .map((choice) => choice.label);
}

export interface FieldSelection {
  picked: Record<FieldGroupKey, string[]>;
  custom: Record<FieldGroupKey, CustomField[]>;
}

export const initialFieldSelection = (): FieldSelection => ({
  picked: {
    header: defaultSelection("header"),
    lineItems: defaultSelection("lineItems"),
    bom: defaultSelection("bom"),
  },
  custom: { header: [], lineItems: [], bom: [] },
});

/** The groups shown for a case: BOM fields only make sense with BOMs. */
export const groupsFor = (mode: UseCaseMode): FieldGroupKey[] =>
  mode === "single" ? ["header", "lineItems"] : ["header", "lineItems", "bom"];

/** Ticked choices plus the user's own fields of one group. */
export function fieldsOf(
  group: FieldGroupKey,
  selection: FieldSelection,
): CustomField[] {
  const chosen = FIELD_GROUPS[group].choices
    .filter((choice) => selection.picked[group].includes(choice.label))
    .map(({ label, description }) => ({ name: label, description }));
  return [...chosen, ...selection.custom[group]];
}

const line = ({ name, description }: CustomField) =>
  description ? `- ${name} (${description})` : `- ${name}`;

const section = (intro: string, fields: CustomField[]) =>
  fields.length > 0 ? `${intro}\n${fields.map(line).join("\n")}` : "";

/** Whether the selection is enough to describe an extraction for this case. */
export function hasEnoughFields(
  mode: UseCaseMode,
  selection: FieldSelection,
): boolean {
  const po =
    fieldsOf("header", selection).length +
    fieldsOf("lineItems", selection).length;
  return po > 0 && (mode === "single" || fieldsOf("bom", selection).length > 0);
}

/** The prompt for the ticked and own fields. Mirrors the style of the editable prompts. */
export function composeFromFields(
  mode: UseCaseMode,
  selection: FieldSelection,
): string {
  const header = fieldsOf("header", selection);
  const items = fieldsOf("lineItems", selection);
  if (mode === "single") {
    return [
      "Extract purchase order data.",
      section(
        "The output will include the following top-level fields:",
        header,
      ),
      items.length > 0
        ? "Also, the output will include the data for each line item."
        : "",
      section("For each line item, extract these scalar fields:", items),
    ]
      .filter(Boolean)
      .join("\n\n");
  }
  return [
    "Extract data from a purchase order (PO) and its bills of materials (BOMs). " +
      "The PO may have several items. Each item is linked to its BOM by the material number, " +
      "which the BOM holds as its material ID. Always include the material number of each item.",
    section("Extract these header fields from the PO:", header),
    section("For every item in the PO, extract:", items),
    section(
      "From the BOM with the matching material number, add to each item:",
      fieldsOf("bom", selection),
    ),
    "The output has one line per PO item.",
  ]
    .filter(Boolean)
    .join("\n\n");
}
