import type { FieldSpec } from "@/components/field-schema-editor";

/**
 * The agreed output fields as the wizard_api reports them, read from the
 * agent's draft blueprint (`target_output_spec`). Mirrors the API model.
 */
export type TargetOutputSpec = {
  schemaName: string;
  fields: string[];
  fieldTypes: Record<string, string>;
  requiredFields: string[];
  optionalFields: string[];
  fieldDescriptions: Record<string, string>;
  allowedValues: Record<string, string[]>;
  missingValuePolicy: string;
  validationRules: string[];
};

// V1 `field_types` values (ExtractionRequirements enum) → the field-schema
// editor's own type vocabulary. A field with allowed values is an enum
// regardless of its declared type, because that is what the reviewer sees.
const TYPE_MAP: Record<string, FieldSpec["type"]> = {
  str: "text",
  int: "number",
  float: "number",
  decimal: "number",
  bool: "boolean",
  date: "date",
  "list[str]": "text",
  "list[dict]": "text",
};

/**
 * Project the API's target output spec onto the rows the field-schema editor
 * renders. Returns an empty array when no fields have been agreed yet, which
 * is the signal to keep showing the example data instead.
 */
export function fieldSpecsFromTargetOutput(
  spec: TargetOutputSpec | null | undefined,
): FieldSpec[] {
  if (!spec?.fields.length) return [];

  const required = new Set(spec.requiredFields);
  // `leave_empty` is the wizard's own wording for "no default, leave blank".
  const missingBehavior: FieldSpec["missingBehavior"] =
    spec.missingValuePolicy && spec.missingValuePolicy !== "leave_empty"
      ? "default"
      : "empty";

  return spec.fields.map((name) => {
    const allowedValues = spec.allowedValues[name];
    const declared = TYPE_MAP[spec.fieldTypes[name]] ?? "text";
    return {
      name,
      type: allowedValues?.length ? "enum" : declared,
      ...(allowedValues?.length ? { allowedValues } : {}),
      required: required.has(name),
      missingBehavior,
      rule: spec.fieldDescriptions[name] || undefined,
    };
  });
}
