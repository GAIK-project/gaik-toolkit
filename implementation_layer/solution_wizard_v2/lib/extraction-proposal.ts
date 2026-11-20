import type { FieldSpec } from "@/components/field-schema-editor";
import { humanize } from "@/lib/case-process";
import { fillTemplate } from "@/lib/chat-template";
import type { TargetOutputSpec } from "@/lib/target-output-spec";

/**
 * The extraction proposal the agent writes in Phase 4 (`extraction_requirements.md`)
 * and the generated field definitions (`output_schema.py`) once approved (#251).
 */
export type ExtractionProposal = {
  promptMarkdown: string;
  schemaGenerated: boolean;
  schemaCode?: string;
};

export type ExtractionProposalStatus = "awaiting_approval" | "approved" | "none";

export type ExtractionProposalLabels = {
  heading: string;
  headingTicket: string;
  leftEmpty: string;
  defaultValue: string;
  noDefault: string;
};

export type ReadableField = {
  /** Raw technical identifier (`equipment_id`), kept for technical details. */
  key: string;
  /** Human-readable label shown in the main list. */
  label: string;
  type: FieldSpec["type"];
  required: boolean;
  /** Plain description without the example clause or raw `null` wording. */
  description?: string;
  /** Example value(s) extracted from the rule or prompt markdown. */
  example?: string;
  allowedValues?: string[];
  /** Clear plain-language wording for missing values. */
  missingText: string;
};

const TICKET_HINT = /\b(tiket\w*|huoltotiket\w*|ticket\w*|maintenance.?ticket|service.?ticket|work.?order)\b/i;

/** Plain-language heading for the extraction proposal in the workspace. */
export function extractionProposalHeading(
  labels: Pick<ExtractionProposalLabels, "heading" | "headingTicket">,
  ...hints: Array<string | null | undefined>
): string {
  const joined = hints.filter(Boolean).join(" ");
  return TICKET_HINT.test(joined) ? labels.headingTicket : labels.heading;
}

/**
 * Whether the extraction proposal currently awaits the user's explicit approval
 * ("Hyväksy poimintaohje" / "Pyydä muutoksia") in the workspace.
 */
export function extractionProposalStatus(input: {
  wizardStep: number;
  gate1Approved: boolean;
  fieldCount: number;
  proposal?: ExtractionProposal | null;
}): ExtractionProposalStatus {
  const { wizardStep, gate1Approved, fieldCount, proposal } = input;
  if (proposal?.schemaGenerated) return "approved";
  // Approval requires the written extraction rules prompt (extraction_requirements.md),
  // never just the draft blueprint's field list (#251).
  if (proposal?.promptMarkdown.trim()) {
    return gate1Approved ? "awaiting_approval" : "none";
  }
  if (fieldCount > 0 && wizardStep >= 6) return "approved";
  return "none";
}

type PromptFieldMeta = { label?: string; example?: string; description?: string };

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Best-effort read of human labels and examples per field key from
 * `extraction_requirements.md`. Recognises common bullet/heading patterns such as:
 * - `**Laitteen tunnus** (`equipment_id`): ... (esim. Pumppu-04)`
 * - `- **equipment_id** (Laitteen tunnus): ...`
 * - `### Laitteen tunnus (`equipment_id`)`
 */
function parsePromptMetadata(markdown: string, fieldNames: string[]): Map<string, PromptFieldMeta> {
  const out = new Map<string, PromptFieldMeta>();
  if (!markdown.trim() || fieldNames.length === 0) return out;
  const lines = markdown.split(/\r?\n/);

  for (const name of fieldNames) {
    const keyRe = new RegExp(`(?:^|[^A-Za-z0-9_])${escapeRegExp(name)}(?:$|[^A-Za-z0-9_])`);
    const lineIdx = lines.findIndex((line) => keyRe.test(line));
    if (lineIdx < 0) continue;
    const line = lines[lineIdx].trim();
    const meta: PromptFieldMeta = {};

    // Pattern 1: "**Laitteen tunnus** (`equipment_id`)" or "### Laitteen tunnus (equipment_id)"
    const beforeKey = new RegExp(
      `^(?:[-*+]\\s+|#+\\s+|\\d+\\.\\s+)?(?:\\*\\*)?([^(*:\\n\`]{2,60}?)(?:\\*\\*)?\\s*\\(\\s*\`?${escapeRegExp(name)}\`?\\s*\\)`,
    ).exec(line);
    if (beforeKey) {
      const candidate = beforeKey[1].trim();
      if (candidate && candidate.toLowerCase() !== name.toLowerCase()) meta.label = candidate;
    }

    // Pattern 2: "- **equipment_id** (Laitteen tunnus):"
    if (!meta.label) {
      const afterKey = new RegExp(
        `\`?${escapeRegExp(name)}\`?(?:\\*\\*)?\\s*\\(\\s*([^)\\n\`]{2,60}?)\\s*\\)`,
      ).exec(line);
      if (afterKey) {
        const candidate = afterKey[1].trim();
        if (
          candidate &&
          !/^(?:str|int|float|bool|date|decimal|list|optional|required|pakollinen|valinnainen|null|string|number)/i.test(
            candidate,
          ) &&
          !/^(?:esim\.?|e\.g\.?|example)/i.test(candidate)
        ) {
          meta.label = candidate;
        }
      }
    }

    // Look for an example on the same line or the next couple of indented/bullet lines.
    const block = [line];
    for (let j = lineIdx + 1; j < Math.min(lines.length, lineIdx + 5); j++) {
      const next = lines[j];
      if (!next.trim() || /^#+\s/.test(next.trim())) break;
      if (/^[-*+]\s+/.test(next) && fieldNames.some((other) => other !== name && next.includes(other))) break;
      block.push(next.trim());
    }
    const { example } = extractExample(block.join(" "));
    if (example) meta.example = example;

    out.set(name, meta);
  }
  return out;
}

/** Pulls an inline example ("(esim. ...)", "esim. ...", "e.g. ...", "Esimerkki: ...") out of text. */
export function extractExample(text: string): { cleaned: string; example?: string } {
  const trimmed = text.trim();
  if (!trimmed) return { cleaned: "" };

  // Parenthesised example: "(esim. Pumppu-04, IV-kone 2)" or "(e.g., Pump-04)"
  const parenRe = /\(\s*(?:esim\.?|esimerkiksi|esimerkki|e\.g\.?,?|example:?)\s*([^()]+)\)/i;
  const parenMatch = parenRe.exec(trimmed);
  if (parenMatch) {
    const example = parenMatch[1].trim().replace(/[.;,\s]+$/, "");
    const cleaned = trimmed
      .replace(parenMatch[0], "")
      .replace(/\s{2,}/g, " ")
      .replace(/\s+([.,;:])/g, "$1")
      .trim();
    if (example) return { cleaned, example };
  }

  // Trailing or standalone clause: "Esimerkki: ..." / "Example: ..." / "esim. ..."
  const clauseRe = /(?:^|[.;\n]\s*)(?:esimerkki|example|esim\.?|e\.g\.?)\s*:?\s+([^\n.;]+)/i;
  const clauseMatch = clauseRe.exec(trimmed);
  if (clauseMatch) {
    const example = clauseMatch[1].trim().replace(/[.;,\s]+$/, "");
    const cleaned = trimmed
      .replace(clauseMatch[0], "")
      .replace(/\s{2,}/g, " ")
      .trim();
    if (example) return { cleaned, example };
  }

  return { cleaned: trimmed };
}

/** Replaces raw `null` / `leave_empty` wording in field descriptions with plain words. */
export function cleanTechnicalWording(text: string, leftEmpty: string): string {
  return text
    .replace(/\b(?:palauta|aseta|käytä|return|set to|use)\s+(?:`null`|null\b)/gi, leftEmpty.toLowerCase())
    .replace(/`null`/g, `"${leftEmpty.toLowerCase()}"`)
    .replace(/\bleave_empty\b/gi, leftEmpty.toLowerCase())
    .trim();
}

/** Plain-language missing-value policy for one field. */
export function missingPolicyText(
  field: Pick<FieldSpec, "missingBehavior" | "defaultValue">,
  policy: string | undefined,
  labels: Pick<ExtractionProposalLabels, "leftEmpty" | "defaultValue" | "noDefault">,
): string {
  if (field.missingBehavior === "empty") return labels.leftEmpty;
  if (field.defaultValue) {
    return fillTemplate(labels.defaultValue, { value: field.defaultValue });
  }
  const normalized = (policy ?? "").trim();
  if (!normalized || /^(?:leave_empty|null|none|empty|blank)$/i.test(normalized)) {
    return labels.leftEmpty;
  }
  return cleanTechnicalWording(normalized, labels.leftEmpty);
}

/** Build readable field rows for the workspace extraction proposal view. */
export function buildReadableFields(
  fields: FieldSpec[],
  spec: TargetOutputSpec | null | undefined,
  promptMarkdown: string | undefined,
  labels: ExtractionProposalLabels,
): ReadableField[] {
  const promptMeta = parsePromptMetadata(
    promptMarkdown ?? "",
    fields.map((f) => f.name),
  );
  return fields.map((field) => {
    const meta = promptMeta.get(field.name);
    const rawRule = field.rule ?? "";
    const { cleaned, example: ruleExample } = extractExample(rawRule);
    const description = cleaned ? cleanTechnicalWording(cleaned, labels.leftEmpty) : undefined;
    const example = ruleExample ?? meta?.example;
    return {
      key: field.name,
      label: meta?.label || humanize(field.name),
      type: field.type,
      required: field.required,
      ...(description ? { description } : {}),
      ...(example ? { example } : {}),
      ...(field.allowedValues?.length ? { allowedValues: field.allowedValues } : {}),
      missingText: missingPolicyText(field, spec?.missingValuePolicy, labels),
    };
  });
}
