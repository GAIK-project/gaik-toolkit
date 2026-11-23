import type { FieldSpec } from "@/components/field-schema-editor";
import { fillTemplate, quoteOneLine } from "@/lib/chat-template";

// The output schema's fields are edited where they are listed (the Blueprint
// tab's "Tulosskeema"). The agreed fields live in the wizard's own draft
// (target_output_spec), which only the wizard writes: the page has no route
// that saves them. So the edit becomes one chat turn that names each change,
// and the wizard applies it, as it does a correction typed in the chat.

export const FIELD_TYPES = ["text", "number", "date", "boolean", "enum"] as const satisfies readonly FieldSpec["type"][];

/** One row of the form. */
export type FieldDraft = {
  /** Stable for the row's lifetime, also while its name is being typed. */
  key: string;
  /** The field's name as agreed; null for a row the user added. */
  original: string | null;
  name: string;
  type: FieldSpec["type"];
  required: boolean;
  /** An enum's values as typed, comma-separated. */
  values: string;
};

export function draftsFromFields(fields: FieldSpec[]): FieldDraft[] {
  return fields.map((field, i) => ({
    key: `field-${i}`,
    original: field.name,
    name: field.name,
    type: field.type,
    required: field.required,
    values: (field.allowedValues ?? []).join(", "),
  }));
}

/** The values typed into one field: trimmed, without empties or repeats. */
export function valuesOf(text: string): string[] {
  return [...new Set(text.split(/[,;\n]/).map((v) => v.trim()).filter(Boolean))];
}

export type FieldDraftProblem = "name" | "duplicate" | "values";

/** Why the rows cannot be sent yet: a row has no name, two share one, or a choice has no values. */
export function fieldDraftProblem(drafts: FieldDraft[]): FieldDraftProblem | null {
  const names = drafts.map((d) => d.name.trim());
  if (names.some((name) => !name)) return "name";
  if (new Set(names).size !== names.length) return "duplicate";
  if (drafts.some((d) => d.type === "enum" && valuesOf(d.values).length === 0)) return "values";
  return null;
}

export type FieldChange =
  | { kind: "add"; name: string; type: FieldSpec["type"]; required: boolean; values: string[] }
  | {
      kind: "change";
      original: string;
      /** Only what differs from the agreed field. */
      name?: string;
      type?: FieldSpec["type"];
      required?: boolean;
      values?: string[];
    }
  | { kind: "remove"; original: string };

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((v, i) => v === b[i]);

/** What the rows change in the agreed fields, in the rows' order; removals last. */
export function fieldChanges(fields: FieldSpec[], drafts: FieldDraft[]): FieldChange[] {
  const agreed = new Map(fields.map((field) => [field.name, field]));
  const changes: FieldChange[] = [];
  const kept = new Set<string>();

  for (const draft of drafts) {
    const name = draft.name.trim();
    const values = draft.type === "enum" ? valuesOf(draft.values) : [];
    const before = draft.original === null ? undefined : agreed.get(draft.original);
    if (!before) {
      changes.push({ kind: "add", name, type: draft.type, required: draft.required, values });
      continue;
    }
    kept.add(before.name);
    const change: Extract<FieldChange, { kind: "change" }> = { kind: "change", original: before.name };
    if (name !== before.name) change.name = name;
    if (draft.type !== before.type) change.type = draft.type;
    if (draft.required !== before.required) change.required = draft.required;
    if (draft.type === "enum" && !sameList(values, before.allowedValues ?? [])) change.values = values;
    if (Object.keys(change).length > 2) changes.push(change);
  }
  for (const field of fields) {
    if (!kept.has(field.name)) changes.push({ kind: "remove", original: field.name });
  }
  return changes;
}

export type FieldChangeLabels = {
  /** The message's first line. */
  intro: string;
  /** {name} and {details}. */
  add: string;
  /** {name} and {details}. */
  change: string;
  /** {name}. */
  remove: string;
  /** {name}: the field's new name. */
  renamed: string;
  /** {type}. */
  type: string;
  required: string;
  optional: string;
  /** {values}. */
  values: string;
  types: Record<FieldSpec["type"], string>;
};

/**
 * The chat turn that asks the wizard for the changes: one line per field. A
 * field's agreed name is the wizard's text, so it goes as a quote on one line.
 * Empty when nothing changed.
 */
export function fieldChangeMessage(changes: FieldChange[], labels: FieldChangeLabels): string {
  if (!changes.length) return "";
  const lines = changes.map((change) => {
    if (change.kind === "remove") {
      return fillTemplate(labels.remove, { name: quoteOneLine(change.original, 120) });
    }
    const details: string[] = [];
    if (change.kind === "change" && change.name !== undefined) {
      details.push(fillTemplate(labels.renamed, { name: quoteOneLine(change.name, 120) }));
    }
    if (change.type !== undefined) {
      details.push(fillTemplate(labels.type, { type: labels.types[change.type].toLocaleLowerCase() }));
    }
    if (change.required !== undefined) details.push(change.required ? labels.required : labels.optional);
    if (change.values?.length) {
      details.push(fillTemplate(labels.values, { values: quoteOneLine(change.values.join(", ")) }));
    }
    return fillTemplate(change.kind === "add" ? labels.add : labels.change, {
      name: quoteOneLine(change.kind === "add" ? change.name : change.original, 120),
      details: details.join(", "),
    });
  });
  return [labels.intro, ...lines].join("\n");
}
