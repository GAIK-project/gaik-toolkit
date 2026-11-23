import type { PocRunOutput } from "./poc-run-output";

/**
 * Where each value of a run's result comes from.
 *
 * A PoC with SourceTracing writes `<input>_source_trace.json` beside its
 * result: for every extracted value the snippet of the source the model gave
 * as evidence, checked against the text it read. The PoC tab listed that file
 * among the output files and showed one "grounding check" badge; which value
 * rests on which words stayed in the JSON. This reads it for the result view.
 */

/** gaik's verdict on one citation: found as quoted, to be checked by a person,
 *  found in other words, or not checked at all. */
export type TraceVerdict = "verified" | "check" | "reworded" | "unchecked";

export type TracedSource = {
  /** Path of the value in the result, e.g. `total` or `lines[0].quantity`. */
  field: string;
  /** The snippet of the source given as evidence. */
  quote: string;
  verdict: TraceVerdict;
  /** 1-based page in a PDF; null for a text source. */
  page: number | null;
  /** The source document's name when the run named its documents. */
  document: string | null;
  /** The record the value belongs to when the result has several; null when shared. */
  record: number | null;
};

export type SourceTrace = {
  sources: TracedSource[];
  /** Citations found in the source as quoted. */
  verified: number;
  total: number;
};

const TRACE_FILE = /_source_trace\.json$/i;
const VERDICTS: ReadonlySet<string> = new Set(["verified", "check", "reworded", "unchecked"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sourcesOf(body: string): TracedSource[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return [];
  }
  if (!isRecord(parsed) || !Array.isArray(parsed.sources)) return [];
  const documents = Array.isArray(parsed.documents)
    ? parsed.documents.filter((d): d is string => typeof d === "string")
    : [];
  const sources: TracedSource[] = [];
  for (const raw of parsed.sources) {
    if (!isRecord(raw) || typeof raw.field !== "string" || !raw.field) continue;
    const quote = typeof raw.quote === "string" ? raw.quote.trim() : "";
    // A citation without a snippet shows nothing a reader could check.
    if (!quote) continue;
    const number = typeof raw.document === "number" ? raw.document : 0;
    sources.push({
      field: raw.field,
      quote,
      verdict: VERDICTS.has(raw.verdict as string) ? (raw.verdict as TraceVerdict) : "unchecked",
      // Pages mean something only where the run named its documents (PDFs).
      page: documents.length > 0 && typeof raw.page === "number" && raw.page > 0 ? raw.page : null,
      document: documents[number - 1] ?? null,
      record: typeof raw.record === "number" ? raw.record : null,
    });
  }
  return sources;
}

/** The run's source trace, or null when the PoC wrote none (or none that reads). */
export function sourceTraceIn(output: Pick<PocRunOutput, "files">): SourceTrace | null {
  const sources = output.files
    .filter((file) => TRACE_FILE.test(file.name))
    .flatMap((file) => sourcesOf(file.body));
  if (sources.length === 0) return null;
  return {
    sources,
    verified: sources.filter((s) => s.verdict === "verified").length,
    total: sources.length,
  };
}

/** The result field a citation's path starts at: `lines[0].quantity` → `lines`. */
export function topField(path: string): string {
  return path.split(/[.[]/, 1)[0];
}

const rowsOf = (value: unknown): number => (Array.isArray(value) ? value.length : 1);

/**
 * The citations for one field of one result, in the order the model gave them.
 *
 * gaik numbers a citation's `record` the way its demos unwrap results into
 * rows: a result without a list of records is one row, and a result with one
 * is a row per entry of that list, counted on across the results. So for a
 * result shown whole, with its list as a table, the path says which entry a
 * citation is for (`lines[1].quantity`) and `record` only says which result:
 * with one result every citation of the field is its own, and with several the
 * rows before this result are counted off. A citation without a record is one
 * every result shares.
 */
export function sourcesForField(
  trace: SourceTrace | null,
  field: string,
  record: number,
  results: readonly Record<string, unknown>[] = [],
): TracedSource[] {
  if (!trace) return [];
  const own = trace.sources.filter((source) => topField(source.field) === field);
  if (results.length <= 1) return own;
  const first = results.slice(0, record).reduce((rows, result) => rows + rowsOf(result[field]), 0);
  const count = rowsOf(results[record]?.[field]);
  return own.filter((source) => {
    if (source.record === null) return true;
    if (!source.field.startsWith(`${field}[`)) return source.record === record;
    return source.record >= first && source.record < first + count;
  });
}

/** The part of a citation's path below its field, for a list's rows: `lines[0].quantity` → `[0].quantity`. */
export function pathBelowField(path: string): string {
  return path.slice(topField(path).length).replace(/^\./, "");
}
