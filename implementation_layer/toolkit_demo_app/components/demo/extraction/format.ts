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
