// Small helpers for showing extracted records.

/** "people_involved" -> "People involved". */
export function labelOf(key: string): string {
  const text = key.replace(/[_-]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function hasContent(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim() !== "";
  if (Array.isArray(value)) return value.some(hasContent);
  return true;
}

/** The text pieces of a value: a list gives one piece per item. */
export function valueStrings(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(valueStrings);
  if (value === null || value === undefined) return [];
  if (typeof value === "object") return [JSON.stringify(value)];
  const text = String(value).trim();
  return text ? [text] : [];
}

/**
 * Splits the source around the first (case-insensitive) occurrence of the value, so the
 * match can be highlighted. Returns null when the value is not quoted in the source.
 */
export function splitAround(
  source: string,
  needle: string,
): [string, string, string] | null {
  const wanted = needle.trim();
  if (wanted.length < 2) return null;
  const at = source.toLowerCase().indexOf(wanted.toLowerCase());
  if (at < 0) return null;
  return [
    source.slice(0, at),
    source.slice(at, at + wanted.length),
    source.slice(at + wanted.length),
  ];
}

/** What the model quoted as the evidence of one value, and where that quote is in the text. */
export interface TracedSource {
  field: string;
  quote: string;
  value: unknown;
  /** "found": the quote is in the text. Otherwise the model did not copy it exactly. */
  status: string;
  /** Character offsets of the quote in the source text; null when it was not found. */
  span: [number, number] | null;
  /** The record (as the demo unwraps them) the value is in; null for one every record shares. */
  record: number | null;
  /**
   * How far the quote backs the value: verified; check (the quote is not in the text, or
   * holds another number or date); reworded (a text in the model's own words); unchecked.
   */
  verdict?: "verified" | "check" | "reworded" | "unchecked";
}

/** How many values are verified and how many are to be checked. */
export function countVerdicts(sources: TracedSource[] | undefined | null): {
  verified: number;
  check: number;
} {
  const all = sources ?? [];
  return {
    verified: all.filter((source) => source.verdict === "verified").length,
    check: all.filter((source) => source.verdict === "check").length,
  };
}

/** Why a value is to be checked, in words for the person reading the report. */
export function checkReason(source: TracedSource): string {
  return source.status === "found"
    ? "The quote has a different number or date."
    : "The quote is not in the text.";
}

/**
 * The source of a value the person clicked: the entry whose value shows as this text, in
 * this record. A value that appears twice in one record gives the first.
 */
export function sourceFor(
  sources: TracedSource[] | undefined | null,
  text: string,
  record: number,
): TracedSource | null {
  const matches = (sources ?? []).filter(
    (source) =>
      valueStrings(source.value).includes(text) &&
      (source.record === null || source.record === record),
  );
  // One that belongs to this very record is better than one every record shares.
  return (
    matches.find((source) => source.record === record) ?? matches[0] ?? null
  );
}

/**
 * The records of an extraction. A schema with a list of records gives one item that
 * holds the list; a flat schema gives one item per record. Both come out as a list of
 * records.
 */
export function unwrapRecords(
  data: Record<string, unknown>[],
): Record<string, unknown>[] {
  const isRecord = (v: unknown): v is Record<string, unknown> =>
    typeof v === "object" && v !== null && !Array.isArray(v);
  const out: Record<string, unknown>[] = [];
  for (const item of data) {
    const lists = Object.entries(item).filter(
      ([, value]) =>
        Array.isArray(value) && value.length > 0 && value.every(isRecord),
    );
    if (lists.length === 1) {
      const [key, entries] = lists[0];
      const shared = Object.fromEntries(
        Object.entries(item).filter(([k]) => k !== key),
      );
      for (const entry of entries as Record<string, unknown>[]) {
        out.push({ ...shared, ...entry });
      }
    } else {
      out.push(item);
    }
  }
  return out;
}

export type Tone = "low" | "medium" | "high" | "critical";

/** Reads a severity word out of a value such as "Medium" or "low (minor bruising)". */
export function severityOf(value: unknown): Tone | null {
  const text = valueStrings(value).join(" ").toLowerCase();
  for (const tone of ["critical", "high", "medium", "low"] as const) {
    if (new RegExp(`\\b${tone}\\b`).test(text)) return tone;
  }
  return null;
}

export const isSeverityKey = (key: string) => /severity|risk/i.test(key);
