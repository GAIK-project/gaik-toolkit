import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  composeFromFields,
  type FieldSelection,
  initialFieldSelection,
} from "./custom-fields";
import {
  composePrompt,
  initialPromptState,
  newItem,
  TEMPLATES,
} from "./prompt-template";

const SINGLE = `Extract purchase order data.

The output will include the following top-level fields:
- Purchase order date (DD/MM/YYYY format when unambiguous)
- Delivery date (DD/MM/YYYY format when unambiguous)
- Purchase order number (separated by a dash after every 4 digits)
- Supplier number
- Shipping address (Format: company name, street number, postal code, city, country)

Also, the output will include the data for each line item.

For each line item, extract these scalar fields:
- Item number (e.g., 010, 020)
- Description (the item's name, not its technical specification)
- Quantity (text string including the unit, e.g., "8.600 LB")
- Price per currency
- Material number`;

const MULTI = `The task is to extract key fields from customer documents (Purchase Order (PO) and Bill of Material (BOM)), and align them so that each PO item is enriched with the correct technical details. Begin with the customer's purchase order, which may include multiple items. Each item is linked to its BOM via a Material Number.

For every item in the PO, extract the Material Number along with the basic item details: Quantity, Description, and Delivery Date (Format: DD/MM/YYYY). Use the item's Material Number from the PO to find the BOM having the same Material Number (represented as 'ID'). From the matching BOM, extract the part's 'Part Designation' and part dimension (length followed by unit, e.g., 1487mm).

The final output should contain as many lines as the number of items in the PO. Each line should have: Material Number, Quantity, Description, Delivery Date (from PO), Part Designation, part dimension (from BOM).

Also, extract the following header information from the PO: Order Date, Buyer, Sales Person, Shipping Address, Payment Terms.`;

test("the untouched templates reproduce the original prompts", () => {
  expect(composePrompt("single", initialPromptState("single"))).toBe(SINGLE);
  expect(composePrompt("multi", initialPromptState("multi"))).toBe(MULTI);
});

test("editing a token or an item changes only that part of the prompt", () => {
  const state = initialPromptState("multi");
  state.tokens.bomKey = "Material ID";
  state.lists.header[0].text = "Order Date (DD.MM.YYYY)";

  const prompt = composePrompt("multi", state);

  expect(prompt).toContain("(represented as 'Material ID')");
  expect(prompt).toContain("PO: Order Date (DD.MM.YYYY), Buyer,");
  expect(prompt).toContain("Quantity, Description, and Delivery Date");
});

test("added items are written in, empty and removed items are not", () => {
  const state = initialPromptState("single");
  state.lists.header = [
    ...state.lists.header.slice(1),
    newItem("Currency"),
    newItem("   "),
  ];

  const prompt = composePrompt("single", state);

  expect(prompt).not.toContain("- Purchase order date");
  expect(prompt).toContain("- Shipping address (Format: company name");
  expect(prompt).toContain("- Currency\n\nAlso");
});

test("lists of two or three items read as prose", () => {
  const state = initialPromptState("multi");
  state.lists.poItem = [newItem("Quantity"), newItem("Description")];
  expect(composePrompt("multi", state)).toContain(
    "details: Quantity and Description.",
  );

  state.lists.poItem = [newItem("Quantity")];
  expect(composePrompt("multi", state)).toContain("details: Quantity.");
});

test("every editable part of a template has a starting value", () => {
  for (const mode of ["single", "multi"] as const) {
    const state = initialPromptState(mode);
    for (const segment of TEMPLATES[mode].segments) {
      if (segment.type === "token")
        expect(state.tokens[segment.key]).toBeTruthy();
      if (segment.type === "list")
        expect(state.lists[segment.key].length).toBeGreaterThan(0);
    }
  }
});

test("the two line item sentences can be removed one at a time or together", () => {
  const state = initialPromptState("single");
  const LINE_NOTE =
    "Also, the output will include the data for each line item.";
  const LINE_INTRO = "For each line item, extract these scalar fields:";

  state.removed.lineItemsNote = true;
  const withoutNote = composePrompt("single", state);
  expect(withoutNote).not.toContain(LINE_NOTE);
  expect(withoutNote).toContain(LINE_INTRO);

  state.removed.lineItemsNote = false;
  state.removed.lineItemsIntro = true;
  const withoutIntro = composePrompt("single", state);
  expect(withoutIntro).toContain(LINE_NOTE);
  expect(withoutIntro).not.toContain(LINE_INTRO);

  state.removed.lineItemsNote = true;
  const withoutBoth = composePrompt("single", state);
  expect(withoutBoth).not.toContain("line item.");
  expect(withoutBoth).toContain("- Item number (e.g., 010, 020)");
  // Removing sentences never leaves more than one blank line.
  expect(withoutBoth).not.toContain("\n\n\n");

  // Putting them back restores the original prompt.
  state.removed = {};
  expect(composePrompt("single", state)).toBe(SINGLE);
});

test("the material number is one editable name used throughout the multi prompt", () => {
  const state = initialPromptState("multi");
  expect(composePrompt("multi", state).match(/Material Number/g)?.length).toBe(
    5,
  );

  state.tokens.materialNumber = "Part No";
  const prompt = composePrompt("multi", state);

  // Four mentions in the prose follow the token; the output column is its own item.
  expect(prompt.match(/Part No/g)?.length).toBe(4);
  expect(prompt.match(/Material Number/g)?.length).toBe(1);

  // An emptied name falls back to the original instead of leaving a gap.
  state.tokens.materialNumber = "  ";
  expect(composePrompt("multi", state)).toBe(MULTI);
});

test("ticked fields become a prompt for each case", () => {
  const selection: FieldSelection = initialFieldSelection();
  selection.custom.header = [{ name: "Project code", description: "" }];

  const single = composeFromFields("single", selection);
  expect(single).toContain("- PO number (Purchase order number)");
  expect(single).toContain("- Project code\n");
  expect(single).toContain("For each line item, extract these scalar fields:");
  expect(single).not.toContain("Material ID");

  const multi = composeFromFields("multi", selection);
  expect(multi).toContain("From the BOM with the matching material number");
  expect(multi).toContain("- Material ID (Material ID, for example MAT-2401)");
});

test("the server's single-file example prompt is the starting prompt", () => {
  // The example is processed with the prompt in this file, and its saved schema is
  // made from it. Edit both together: change the template, then copy its prompt here.
  const file = join(
    import.meta.dir,
    "../../../api/schemas/luvata_single_example_task.txt",
  );
  const saved = readFileSync(file, "utf-8").replace(/\r\n/g, "\n").trim();

  expect(saved).toBe(composePrompt("single", initialPromptState("single")));
});
