import { describe, expect, it } from "vitest";
import { fieldSpecsFromTargetOutput, type TargetOutputSpec } from "@/lib/target-output-spec";

const spec: TargetOutputSpec = {
  schemaName: "IncidentReport",
  fields: ["asset_id", "severity", "reported_at", "cost"],
  fieldTypes: { asset_id: "str", severity: "str", reported_at: "date", cost: "decimal" },
  requiredFields: ["asset_id", "severity"],
  optionalFields: ["reported_at", "cost"],
  fieldDescriptions: { asset_id: "Asset the incident concerns" },
  allowedValues: { severity: ["low", "high"] },
  missingValuePolicy: "leave_empty",
  validationRules: [],
};

describe("fieldSpecsFromTargetOutput (#141)", () => {
  it("maps declared types and marks required fields", () => {
    const rows = fieldSpecsFromTargetOutput(spec);
    expect(rows.map((r) => [r.name, r.type, r.required])).toEqual([
      ["asset_id", "text", true],
      ["severity", "enum", true],
      ["reported_at", "date", false],
      ["cost", "number", false],
    ]);
  });

  it("treats a field with allowed values as an enum and carries them through", () => {
    const severity = fieldSpecsFromTargetOutput(spec)[1];
    expect(severity.allowedValues).toEqual(["low", "high"]);
  });

  it("passes the field description through as the extraction rule", () => {
    expect(fieldSpecsFromTargetOutput(spec)[0].rule).toBe("Asset the incident concerns");
    expect(fieldSpecsFromTargetOutput(spec)[1].rule).toBeUndefined();
  });

  it("reads the missing-value policy", () => {
    expect(fieldSpecsFromTargetOutput(spec)[0].missingBehavior).toBe("empty");
    expect(
      fieldSpecsFromTargetOutput({ ...spec, missingValuePolicy: "default" })[0].missingBehavior,
    ).toBe("default");
  });

  it("returns nothing when no fields are agreed yet, so the example data stays", () => {
    expect(fieldSpecsFromTargetOutput(null)).toEqual([]);
    expect(fieldSpecsFromTargetOutput({ ...spec, fields: [] })).toEqual([]);
  });

  it("falls back to text for an unknown declared type", () => {
    const rows = fieldSpecsFromTargetOutput({
      ...spec,
      fields: ["weird"],
      fieldTypes: { weird: "dict" },
      allowedValues: {},
    });
    expect(rows[0].type).toBe("text");
  });
});
