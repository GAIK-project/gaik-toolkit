/**
 * The blueprint's fields in plain words, for a refused edit: wizard_api names
 * the field it refused (`operations[2].step_id`, `after`), and the user reads
 * "the previous step" instead. The words are in the dictionary
 * (`blueprintFieldNames`, lib/i18n), keyed by the field's last name. Step
 * fields for now; later edits add their own keys there.
 */
import type { Dict } from "@/lib/i18n";

/** The last name of a refused field: `operations[0].step_id` → `step_id`; null without one. */
export function blueprintFieldKey(field: string | null | undefined): string | null {
  if (!field) return null;
  const last = field.split(".").pop() ?? "";
  const key = last.replace(/\[\d+\]$/, "");
  return /^[a-z_]+$/.test(key) && !/\[/.test(last) ? key : null;
}

/** The field in the UI language, or null when there are no words for it. */
export function fieldInPlainWords(field: string | null | undefined, t: Pick<Dict, "blueprintFieldNames">): string | null {
  const key = blueprintFieldKey(field);
  if (!key) return null;
  return Object.prototype.hasOwnProperty.call(t.blueprintFieldNames, key) ? t.blueprintFieldNames[key] : null;
}
