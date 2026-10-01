// The two starting prompts for "Create your use case". A prompt is fixed text with
// editable parts: single values ("tokens", which can appear in several places),
// sentences that can be removed ("optional"), and lists of items. The editor shows the
// editable parts highlighted; composePrompt() turns the edited state back into the
// text that is sent to the schema generator.

export type UseCaseMode = "single" | "multi";

/** How the items of a list are written into the prompt. */
export type ListStyle = "bullets" | "comma" | "and";

export type Segment =
  | { type: "text"; text: string }
  | { type: "token"; key: string; label: string }
  | { type: "optional"; key: string; text: string }
  | { type: "list"; key: string; style: ListStyle; label: string };

export interface PromptItem {
  id: string;
  text: string;
  /** Set on items the user just added, so the editor can focus them. */
  fresh?: boolean;
}

export interface PromptState {
  tokens: Record<string, string>;
  lists: Record<string, PromptItem[]>;
  /** Keys of the optional sentences the user has removed. */
  removed: Record<string, boolean>;
}

interface Template {
  segments: Segment[];
  tokens: Record<string, string>;
  lists: Record<string, string[]>;
}

// The material number links each PO item to its BOM, so it is named in several places
// of the multi-file prompt; editing one of them edits all.
const MATERIAL_NUMBER: Segment = {
  type: "token",
  key: "materialNumber",
  label: "What the material number is called",
};

export const TEMPLATES: Record<UseCaseMode, Template> = {
  single: {
    segments: [
      {
        type: "text",
        text: "Extract purchase order data.\n\nThe output will include the following top-level fields:\n",
      },
      {
        type: "list",
        key: "header",
        style: "bullets",
        label: "Add a top-level field",
      },
      { type: "text", text: "\n\n" },
      {
        type: "optional",
        key: "lineItemsNote",
        text: "Also, the output will include the data for each line item.",
      },
      { type: "text", text: "\n\n" },
      {
        type: "optional",
        key: "lineItemsIntro",
        text: "For each line item, extract these scalar fields:",
      },
      { type: "text", text: "\n" },
      {
        type: "list",
        key: "lineItems",
        style: "bullets",
        label: "Add a line item field",
      },
    ],
    tokens: {},
    lists: {
      header: [
        "Purchase order date (DD/MM/YYYY format when unambiguous)",
        "Delivery date (DD/MM/YYYY format when unambiguous)",
        "Purchase order number (separated by a dash after every 4 digits)",
        "Supplier number",
        "Shipping address (Format: company name, street number, postal code, city, country)",
      ],
      lineItems: [
        "Item number (e.g., 010, 020)",
        "Description (the item's name, not its technical specification)",
        'Quantity (text string including the unit, e.g., "8.600 LB")',
        "Price per currency",
        "Material number",
      ],
    },
  },
  multi: {
    segments: [
      {
        type: "text",
        text: "The task is to extract key fields from customer documents (Purchase Order (PO) and Bill of Material (BOM)), and align them so that each PO item is enriched with the correct technical details. Begin with the customer's purchase order, which may include multiple items. Each item is linked to its BOM via a ",
      },
      MATERIAL_NUMBER,
      {
        type: "text",
        text: ".\n\nFor every item in the PO, extract the ",
      },
      MATERIAL_NUMBER,
      {
        type: "text",
        text: " along with the basic item details: ",
      },
      {
        type: "list",
        key: "poItem",
        style: "and",
        label: "Add a PO item detail",
      },
      { type: "text", text: ". Use the item's " },
      MATERIAL_NUMBER,
      { type: "text", text: " from the PO to find the BOM having the same " },
      MATERIAL_NUMBER,
      { type: "text", text: " (represented as '" },
      {
        type: "token",
        key: "bomKey",
        label: "BOM column holding the material number",
      },
      { type: "text", text: "'). From the matching BOM, extract " },
      { type: "list", key: "bomItem", style: "and", label: "Add a BOM detail" },
      {
        type: "text",
        text: ".\n\nThe final output should contain as many lines as the number of items in the PO. Each line should have: ",
      },
      {
        type: "list",
        key: "outputLine",
        style: "comma",
        label: "Add an output column",
      },
      {
        type: "text",
        text: ".\n\nAlso, extract the following header information from the PO: ",
      },
      {
        type: "list",
        key: "header",
        style: "comma",
        label: "Add a header field",
      },
      { type: "text", text: "." },
    ],
    tokens: { bomKey: "ID", materialNumber: "Material Number" },
    lists: {
      poItem: ["Quantity", "Description", "Delivery Date (Format: DD/MM/YYYY)"],
      bomItem: [
        "the part's 'Part Designation'",
        "part dimension (length followed by unit, e.g., 1487mm)",
      ],
      outputLine: [
        "Material Number",
        "Quantity",
        "Description",
        "Delivery Date (from PO)",
        "Part Designation",
        "part dimension (from BOM)",
      ],
      header: [
        "Order Date",
        "Buyer",
        "Sales Person",
        "Shipping Address",
        "Payment Terms",
      ],
    },
  },
};

let freshCounter = 0;

export function newItem(text = ""): PromptItem {
  freshCounter += 1;
  return { id: `new-${freshCounter}`, text, fresh: true };
}

/** The starting values of a template's editable parts. */
export function initialPromptState(mode: UseCaseMode): PromptState {
  const { tokens, lists } = TEMPLATES[mode];
  return {
    tokens: { ...tokens },
    lists: Object.fromEntries(
      Object.entries(lists).map(([key, items]) => [
        key,
        items.map((text, index) => ({ id: `${key}-${index}`, text })),
      ]),
    ),
    removed: {},
  };
}

function joinAnd(items: string[]): string {
  if (items.length <= 2) return items.join(" and ");
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function writeList(items: string[], style: ListStyle): string {
  if (style === "bullets") return items.map((item) => `- ${item}`).join("\n");
  return style === "and" ? joinAnd(items) : items.join(", ");
}

/**
 * The prompt text for the edited state. Empty items are left out, an emptied value
 * falls back to its original, and removed sentences leave no gap.
 */
export function composePrompt(mode: UseCaseMode, state: PromptState): string {
  const { segments, tokens } = TEMPLATES[mode];
  return segments
    .map((segment) => {
      if (segment.type === "text") return segment.text;
      if (segment.type === "optional")
        return state.removed[segment.key] ? "" : segment.text;
      if (segment.type === "token")
        return state.tokens[segment.key]?.trim() || tokens[segment.key];
      const items = (state.lists[segment.key] ?? [])
        .map((item) => item.text.trim())
        .filter(Boolean);
      return writeList(items, segment.style);
    })
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
