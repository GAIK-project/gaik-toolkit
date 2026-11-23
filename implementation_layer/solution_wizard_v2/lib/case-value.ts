/**
 * A result value as a person would write it. The cases view shows what the
 * solution produced, and that is data of any shape: a list is lines, a record
 * is "label: value" lines, a boolean is Yes or No, nothing is a dash. No JSON
 * brackets or quotes reach the page; a shape this cannot read is kept as JSON
 * for a "Show raw" disclosure.
 */
import { humanize } from "@/lib/case-process";

export type ValueWords = {
  yes: string;
  no: string;
  /**
   * An empty list: the solution looked and found none ("No line items"). A
   * missing value is a dash; without this word an empty list is one too.
   */
  none?: string;
  /**
   * How a number of a named field reads, where its name says more than the
   * number: a confidence of 0.93 as "93 %". `among` is the object the number
   * is a field of, or every record of its list, for a reading that depends on
   * its neighbours (a bare 1 is "100 %" only beside a fraction). Undefined
   * leaves it as written.
   */
  number?: (field: string, value: number, among: Record<string, unknown>[]) => string | undefined;
};

export type Pair = { label: string; value: ShownValue };

export type ShownValue =
  | { kind: "empty" }
  | { kind: "text"; text: string }
  /** A list of plain values: one line each. */
  | { kind: "list"; items: string[] }
  /** One object: its fields as "label: value" lines. */
  | { kind: "pairs"; pairs: Pair[] }
  /** A list of objects: each one's fields, under the columns they share. */
  | { kind: "records"; columns: string[]; rows: Pair[][] }
  /** A shape with no plain reading; the JSON, for a disclosure. */
  | { kind: "raw"; json: string };

export const EMPTY_MARK = "—";

/** A record with more fields than this is laid out as pairs, not as a table row. */
export const TABLE_MAX_COLUMNS = 4;
/** A value longer than this needs a line of its own, not a table cell. */
export const TABLE_MAX_TEXT = 80;
/** How deep a value is read: a list of records whose fields hold lists or records. */
const MAX_DEPTH = 2;

const EMPTY: ShownValue = { kind: "empty" };

const isPlain = (v: unknown): v is string | number | boolean | null | undefined =>
  v === null || v === undefined || typeof v !== "object";
const isObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);

function plain(value: string | number | boolean | null | undefined, words: ValueWords): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? words.yes : words.no;
  return String(value).trim();
}

/**
 * Text that is itself a JSON list or object ('["a","b"]') is read as that,
 * where the reading clearly helps: an object with fields, a list of two or
 * more items, or a list of objects. Text that only happens to be valid JSON
 * ("[1]", "[]", "{}") is what its writer wrote, and stays as written.
 */
function parsedJson(text: string): unknown {
  if (!/^[[{]/.test(text) || !/[\]}]$/.test(text)) return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (Array.isArray(parsed)) {
    return parsed.length >= 2 || (parsed.length > 0 && parsed.every(isObject)) ? parsed : undefined;
  }
  return isObject(parsed) && Object.keys(parsed).length > 0 ? parsed : undefined;
}

/** The value of a record's field: as any value, but a number may be said in its field's way. */
function fieldValue(
  key: string,
  value: unknown,
  among: Record<string, unknown>[],
  words: ValueWords,
  depth: number,
): ShownValue {
  const said = typeof value === "number" ? words.number?.(key, value, among) : undefined;
  return said ? { kind: "text", text: said } : formatValue(value, words, depth);
}

function pairsOf(record: Record<string, unknown>, words: ValueWords, depth: number): Pair[] {
  return Object.keys(record).map((key) => ({
    label: humanize(key),
    value: fieldValue(key, record[key], [record], words, depth + 1),
  }));
}

export function formatValue(value: unknown, words: ValueWords, depth = 0): ShownValue {
  if (isPlain(value)) {
    const text = plain(value, words);
    if (!text) return EMPTY;
    const parsed = typeof value === "string" ? parsedJson(text) : undefined;
    return parsed === undefined ? { kind: "text", text } : formatValue(parsed, words, depth);
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return words.none ? { kind: "text", text: words.none } : EMPTY;
    if (value.every(isPlain)) {
      // An empty item keeps its place, as a dash: the third of three answers
      // is still the third. A list of nothing but empty items is empty.
      const items = value.map((item) => plain(item, words));
      return items.some(Boolean) ? { kind: "list", items: items.map((item) => item || EMPTY_MARK) } : EMPTY;
    }
    if (depth < MAX_DEPTH && value.every(isObject)) {
      const columns: string[] = [];
      for (const row of value) for (const key of Object.keys(row)) if (!columns.includes(key)) columns.push(key);
      if (columns.length === 0) return EMPTY;
      // Every row carries every column, so a table has no holes and the pairs
      // of two records line up.
      const rows = value.map((row) =>
        columns.map((key) => ({ label: humanize(key), value: fieldValue(key, row[key], value, words, depth + 1) })),
      );
      return { kind: "records", columns: columns.map(humanize), rows };
    }
  } else if (depth < MAX_DEPTH) {
    const pairs = pairsOf(value as Record<string, unknown>, words, depth);
    return pairs.length ? { kind: "pairs", pairs } : EMPTY;
  }
  return { kind: "raw", json: JSON.stringify(value, null, 2) };
}

/**
 * The value as plain text, for where there is no markup (a printed page) and
 * for measuring it. A list is a line per item; a record's fields are
 * "label: value" lines; records are parted by an empty line.
 */
export function valueText(shown: ShownValue): string {
  switch (shown.kind) {
    case "empty":
      return EMPTY_MARK;
    case "text":
      return shown.text;
    case "list":
      return shown.items.join("\n");
    case "pairs":
      return shown.pairs.map(pairLine).join("\n");
    case "records":
      return shown.rows.map((row) => row.map(pairLine).join("\n")).join("\n\n");
    case "raw":
      return shown.json;
  }
}

/** "Label: value" on one line; a value of several lines hangs under its label. */
export function pairLine({ label, value }: Pair): string {
  const text = valueText(value);
  return text.includes("\n") ? `${label}:\n${text.replace(/^/gm, "  ")}` : `${label}: ${text}`;
}

/**
 * How a list of records is laid out: a table while the fields are few and
 * short, otherwise each record as label and value pairs. Six columns of
 * sentences in one table wrap to a word a line.
 */
export function recordsLayout(shown: Extract<ShownValue, { kind: "records" }>): "table" | "pairs" {
  if (shown.columns.length > TABLE_MAX_COLUMNS) return "pairs";
  const long = shown.rows.some((row) =>
    row.some(({ value }) => value.kind === "raw" || valueText(value).length > TABLE_MAX_TEXT),
  );
  return long ? "pairs" : "table";
}

// -- the grounding check ---------------------------------------------------------

export type GroundingFlag = { field: string; value: ShownValue; reason: string };

/**
 * The values a failed grounding check is about. The generated solution's
 * check writes `hallucination_flags` (field, value, reason) beside `passed`;
 * a check that only says `passed` names none, and the list is empty.
 */
export function groundingFlags(validation: unknown, words: ValueWords): GroundingFlag[] {
  const flags = isObject(validation) ? validation.hallucination_flags : undefined;
  if (!Array.isArray(flags)) return [];
  return flags.filter(isObject).flatMap((flag) => {
    const field = typeof flag.field === "string" ? flag.field.trim() : "";
    const value = flaggedValue(flag.value, words);
    if (!field && value.kind === "empty") return [];
    return [
      {
        field: fieldPathLabel(field),
        value,
        reason: typeof flag.reason === "string" ? flag.reason.trim() : "",
      },
    ];
  });
}

/**
 * A field's path as labels: "line_item.article_code" is a field of a field,
 * and a number in the path ("line_items.0.code", "line_items[0].code") is the
 * place in a list, which people count from one: "Line items › 1 › Code".
 */
export function fieldPathLabel(path: string): string {
  return path
    .replace(/\[(\d+)\]/g, ".$1")
    .split(".")
    .filter(Boolean)
    .map((part) => (/^\d+$/.test(part) ? String(Number(part) + 1) : humanize(part)))
    .join(" › ");
}

/** A Python list of plain single-quoted strings, as str() writes it: ['A', 'B']. */
const PY_STRING = "'[^'\\\\]*'";
const PY_STRING_LIST = new RegExp(`^\\[\\s*${PY_STRING}(?:\\s*,\\s*${PY_STRING})*\\s*\\]$`);

/**
 * A flagged value. The generated check writes it with Python's str(), so
 * nothing is "None", a boolean is "True" or "False" and a list of strings is
 * "['A', 'B']". Those exact shapes are read; anything else is not guessed at
 * and stays as written.
 */
function flaggedValue(value: unknown, words: ValueWords): ShownValue {
  if (typeof value === "string") {
    const text = value.trim();
    if (text === "" || text === "None") return EMPTY;
    if (text === "True" || text === "False") return { kind: "text", text: text === "True" ? words.yes : words.no };
    if (PY_STRING_LIST.test(text)) {
      const items = [...text.matchAll(/'([^'\\]*)'/g)].map((match) => match[1]);
      return formatValue(items, words, MAX_DEPTH - 1);
    }
  }
  return formatValue(value, words, MAX_DEPTH - 1);
}
