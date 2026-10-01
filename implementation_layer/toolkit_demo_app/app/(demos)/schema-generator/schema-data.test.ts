import { describe, expect, test } from "bun:test";
import {
  GALLERY,
  STRUCTURE_ORDER,
  composeBuilderTask,
  diffFields,
  hasChanges,
  initialBuilder,
  newField,
  type SchemaField,
} from "./schema-data";

describe("composeBuilderTask", () => {
  test("describes a single record with its fields and rules", () => {
    const task = composeBuilderTask(initialBuilder()) ?? "";
    expect(task).toContain("Extract a purchase request. It has these fields:");
    expect(task).toContain("- Requester (text): Who asked for it");
    expect(task).toContain("- Priority (one of: low, medium, high)");
    expect(task).toContain("Return null for a value that is not stated.");
  });

  test("marks required fields and skips fields without a name", () => {
    const state = initialBuilder();
    state.fields = [
      newField({ name: "ID", required: true, type: "whole number" }),
      newField({ name: "  " }),
    ];
    const task = composeBuilderTask(state) ?? "";
    expect(task).toContain("- ID (whole number, required)");
    expect(task.match(/^- /gm)?.length).toBe(1);
  });

  test("describes a list of records", () => {
    const state = initialBuilder();
    state.structure = "list";
    const task = composeBuilderTask(state) ?? "";
    expect(task).toContain("Return a list called items");
    expect(task).toContain("- Quantity (whole number)");
    expect(task).not.toContain("Requester");
  });

  test("describes a header with a list inside", () => {
    const state = initialBuilder();
    state.structure = "header-and-list";
    const task = composeBuilderTask(state) ?? "";
    expect(task.indexOf("Header fields:")).toBeLessThan(
      task.indexOf("Return a list called items"),
    );
    expect(task).toContain("- Requester");
    expect(task).toContain("- Item name");
  });

  test("has no task while there is nothing to extract", () => {
    const state = initialBuilder();
    state.fields = [];
    expect(composeBuilderTask(state)).toBeNull();
  });
});

describe("diffFields", () => {
  const field = (
    name: string,
    extra: Partial<SchemaField> = {},
  ): SchemaField => ({
    name,
    type: "text",
    required: false,
    description: name,
    ...extra,
  });

  test("finds added, removed and changed fields, also inside records", () => {
    const before = [
      field("number"),
      field("lines", {
        type: "list of records",
        children: [field("price", { type: "number" }), field("note")],
      }),
    ];
    const after = [
      field("number", { required: true }),
      field("date", { type: "date" }),
      field("lines", {
        type: "list of records",
        children: [field("price", { type: "decimal number" })],
      }),
    ];
    const changes = diffFields(before, after);
    expect(changes.added).toEqual(["date"]);
    expect(changes.removed).toEqual(["lines.note"]);
    expect(changes.changed).toEqual([
      { path: "number", what: "now required" },
      { path: "lines.price", what: "type number → decimal number" },
    ]);
    expect(hasChanges(changes)).toBe(true);
  });

  test("reports no change for equal schemas", () => {
    const fields = [field("a", { allowed: ["x", "y"] })];
    expect(hasChanges(diffFields(fields, fields))).toBe(false);
  });
});

test("the gallery tasks are long enough to be real tasks and have distinct ids", () => {
  expect(new Set(GALLERY.map((g) => g.id)).size).toBe(GALLERY.length);
  for (const item of GALLERY) expect(item.task.length).toBeGreaterThan(120);
});

test("the gallery has two examples of each structure, with their types", () => {
  for (const structure of STRUCTURE_ORDER) {
    const examples = GALLERY.filter((item) => item.structure === structure);
    expect(examples.length).toBe(2);
    for (const example of examples)
      expect(example.types.length).toBeGreaterThan(0);
  }
});
