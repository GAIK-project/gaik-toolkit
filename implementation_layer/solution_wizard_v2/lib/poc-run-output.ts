/**
 * What a sandbox run wrote to `output/`, as the PoC tab shows it.
 *
 * wizard_api reads the run's log between the output markers and answers with
 * the same reading a case gets (`GET /sessions/{id}/runs/{run_id}/output`):
 * the record (the JSON whose keys are the output fields), the grounding check,
 * the transcript, the document, and every printed file. The tab used to show
 * the raw log only, with the result somewhere in it.
 */

import { humanize as fieldLabel, show as valueText } from "./case-process";

export type RunRecord = Record<string, unknown>;
export type RunOutputFile = { name: string; body: string };
/** A file of `output/` the run printed for download, any type (a PDF report). */
export type RunDownload = { name: string; size: number };

export type PocRunOutput = {
  runId: string | null;
  record: RunRecord | RunRecord[] | null;
  validation: (RunRecord & { passed?: boolean }) | null;
  transcript: string;
  document: string;
  files: RunOutputFile[];
  downloads: RunDownload[];
  /** Files over the download limit, named so their absence is not a mystery. */
  skipped: RunDownload[];
};

export const NO_RUN_OUTPUT: PocRunOutput = {
  runId: null,
  record: null,
  validation: null,
  transcript: "",
  document: "",
  files: [],
  downloads: [],
  skipped: [],
};

const isRecord = (v: unknown): v is RunRecord =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function pocRunOutput(raw: unknown): PocRunOutput {
  if (!isRecord(raw)) return NO_RUN_OUTPUT;
  const record = isRecord(raw.record)
    ? raw.record
    : Array.isArray(raw.record) && raw.record.every(isRecord)
      ? (raw.record as RunRecord[])
      : null;
  const files = Array.isArray(raw.files)
    ? raw.files
        .filter(isRecord)
        .filter((f) => typeof f.name === "string" && typeof f.body === "string")
        .map((f) => ({ name: f.name as string, body: f.body as string }))
    : [];
  const sized = (v: unknown): RunDownload[] =>
    Array.isArray(v)
      ? v
          .filter(isRecord)
          .filter((f) => typeof f.name === "string" && typeof f.size === "number")
          .map((f) => ({ name: f.name as string, size: f.size as number }))
      : [];
  return {
    runId: typeof raw.runId === "string" ? raw.runId : typeof raw.run_id === "string" ? raw.run_id : null,
    record,
    validation: isRecord(raw.validation) ? (raw.validation as PocRunOutput["validation"]) : null,
    transcript: typeof raw.transcript === "string" ? raw.transcript : "",
    document: typeof raw.document === "string" ? raw.document : "",
    files,
    downloads: sized(raw.downloads),
    skipped: sized(raw.skipped),
  };
}

/** The run printed at least one output file, as text or for download. */
export const hasRunOutput = (o: PocRunOutput): boolean =>
  o.files.length > 0 || o.downloads.length > 0;

/** The tab's link to one output file of a run. */
export const runFileHref = (sessionId: string, runId: string, name: string): string =>
  `/api/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/files/${encodeURIComponent(name)}`;

/** A file size for people: bytes, kB or MB. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The same labelling and value text as the case view (`lib/case-process`). */
export { humanize as fieldLabel, show as valueText } from "./case-process";

/** How a value reads in the UI language: yes/no, and a percentage ("{n} %"). */
export type ValueWords = { yes: string; no: string; percent: string };

/** A field whose 0-1 number is a confidence: "confidence", "certainty", "conf", "probability". */
export function isConfidenceField(field: string): boolean {
  const f = field.toLowerCase();
  return /confidence|certainty|probability|likelihood/.test(f) || /(^|[_\-\s])conf($|[_\-\s])/.test(f);
}

/**
 * A field that flags a record for a person: "needs_review",
 * "requiresHumanReview", "review_required", "flagged". The name has to say
 * that something is needed: a bare "verification" or "check" set to true more
 * often means the record passed one.
 */
export function isReviewFlagField(field: string): boolean {
  const f = field.toLowerCase().replace(/[^a-z]/g, "");
  if (f === "flagged" || f === "reviewflag") return true;
  const m = /^(needs?|requires?|for)?(human|manual)?(review|check|verification|attention)(needed|required)?$/.exec(f);
  return m !== null && Boolean(m[1] || m[2] || m[4]);
}

const isFlagValue = (v: unknown): boolean =>
  v === null || v === undefined || typeof v === "boolean" || v === "true" || v === "false";

const isScalar = (v: unknown): boolean => v === null || v === undefined || typeof v !== "object";

/**
 * A value as the result shows it: a boolean as yes/no, a 0-1 number under a
 * confidence field as a percentage, anything else as the case view shows it.
 * The tab showed "true", "false" and "0.93".
 */
export function formatValue(
  field: string,
  value: unknown,
  words?: ValueWords,
  percent = isConfidenceField(field),
): string {
  if (words && typeof value === "boolean") return value ? words.yes : words.no;
  if (words && percent && typeof value === "number" && value >= 0 && value <= 1) {
    return words.percent.replace("{n}", String(Math.round(value * 100)));
  }
  return valueText(value);
}

const isFraction = (v: unknown): boolean => typeof v === "number" && v > 0 && v < 1;

/**
 * Whether a confidence field of these records is on the 0-1 scale, so that
 * its numbers read as percentages. A bare 0 or 1 does not say its scale (1 of
 * 5 would read "100 %"), so every number of the field has to lie between 0
 * and 1 and some confidence of the records has to be a fraction. One rule for
 * a record's rows, a table's column and a value nested in a list or object.
 */
function onUnitScale(records: RunRecord[], field: string): boolean {
  if (!isConfidenceField(field)) return false;
  const inRange = records.every((r) => {
    const v = r[field];
    return typeof v !== "number" || (v >= 0 && v <= 1);
  });
  return inRange && records.some((r) => Object.entries(r).some(([f, v]) => isConfidenceField(f) && isFraction(v)));
}

/**
 * A number inside a record's list or object, as lib/case-value's `number`
 * says it: a confidence on the 0-1 scale as a percentage, undefined for any
 * other number. `among` is the object the number is a field of, or every
 * record of its list, and the scale is read from them as `recordRows` reads it.
 */
export function nestedNumber(
  field: string,
  value: number,
  words: ValueWords,
  among: RunRecord[],
): string | undefined {
  return value >= 0 && value <= 1 && onUnitScale(among, field) ? formatValue(field, value, words, true) : undefined;
}

/**
 * The record's fields in the order the run wrote them, each with its value as
 * text. A confidence between 0 and 1 is a percentage. A bare 0 or 1 is a
 * percentage only beside another confidence of the record that is a fraction
 * (`onUnitScale`); otherwise it is shown as the run wrote it. The text stands
 * for a number or a boolean; a list, an object or a text is laid out by the
 * result views (components/result-value).
 */
export function recordRows(
  record: RunRecord,
  words?: ValueWords,
): { field: string; label: string; value: string }[] {
  return Object.entries(record).map(([field, value]) => ({
    field,
    label: fieldLabel(field),
    value: formatValue(field, value, words, onUnitScale([record], field)),
  }));
}

export type RecordTable = {
  columns: { field: string; label: string }[];
  /** One row per record; `flagged` when its review flag is set. */
  rows: { cells: string[]; flagged: boolean }[];
};

/**
 * Two or more flat records as one table: a row per record, a column per field
 * in the order the fields first appear. Two invoices used to be two stacked
 * key/value tables of eight rows each, their value columns at different x.
 * A review flag (needs_review and the like) is not a column but a mark on its
 * row. Null when a single record or a nested value makes a table the wrong
 * shape; the tab then keeps its key/value rendering.
 */
export function recordTable(records: RunRecord[], words: ValueWords): RecordTable | null {
  if (records.length < 2) return null;
  if (!records.every((r) => Object.values(r).every(isScalar))) return null;
  const fields: string[] = [];
  for (const r of records) {
    for (const f of Object.keys(r)) if (!fields.includes(f)) fields.push(f);
  }
  const flags = fields.filter((f) => isReviewFlagField(f) && records.every((r) => isFlagValue(r[f])));
  const shown = fields.filter((f) => !flags.includes(f));
  if (shown.length === 0) return null;
  // A column is percentages or it is not: confidences on a 0-100 or 1-5 scale
  // would otherwise show 87 as "87" and 1 as "100 %" in the same column.
  const percent = new Set(shown.filter((f) => onUnitScale(records, f)));
  return {
    columns: shown.map((field) => ({ field, label: fieldLabel(field) })),
    rows: records.map((r) => ({
      cells: shown.map((f) => formatValue(f, r[f], words, percent.has(f))),
      flagged: flags.some((f) => r[f] === true || r[f] === "true"),
    })),
  };
}

/** One output file of a run: downloadable, readable here, or both. */
export type OutputFileEntry = {
  name: string;
  /** Bytes, when the api listed the file for download. */
  size: number | null;
  /** The text the run printed, when it did. */
  body: string | null;
  downloadable: boolean;
};

/**
 * The run's output files as one list. The same files were listed twice, as
 * download chips and again as a "Tulostiedostot" disclosure holding their text;
 * now each file is listed once, with its download and its text where there is one.
 */
export function outputFileEntries(o: PocRunOutput): OutputFileEntry[] {
  const entries = new Map<string, OutputFileEntry>();
  if (o.runId) {
    for (const d of o.downloads) {
      entries.set(d.name, { name: d.name, size: d.size, body: null, downloadable: true });
    }
  }
  for (const f of o.files) {
    const known = entries.get(f.name);
    if (known) known.body = f.body;
    else entries.set(f.name, { name: f.name, size: null, body: f.body, downloadable: false });
  }
  return [...entries.values()];
}

export type DocumentSection = { title: string; text: string };

/**
 * A document result (a generated report) is a record whose `sections` are
 * titled texts; those read better as a document than as a table. Null for an
 * ordinary record.
 */
export function documentSections(record: RunRecord): DocumentSection[] | null {
  const sections = record.sections;
  if (!Array.isArray(sections) || sections.length === 0 || !sections.every(isRecord)) return null;
  return sections.map((s, i) => ({
    title: typeof s.title === "string" && s.title ? s.title : `${i + 1}`,
    text: valueText(s.text),
  }));
}

/**
 * What the tab says about a run that ended. The done frame carries the Job's
 * `message` and, for a run that did not succeed, a `reason` the api read from
 * the log's last lines (the exception line under the traceback). The reason
 * is the thing to show; the Job's own words name no cause.
 */
export function runEndMessage(evt: {
  phase?: unknown;
  reason?: unknown;
  message?: unknown;
}): string | null {
  const reason = typeof evt.reason === "string" && evt.reason.trim() ? evt.reason.trim() : null;
  const message = typeof evt.message === "string" && evt.message.trim() ? evt.message.trim() : null;
  if (evt.phase === "succeeded") return message;
  return reason ?? message;
}

/** A run the PoC tab picks up again after a reload: where it got to and what to say. */
export type RestoredRun = {
  phase: "running" | "succeeded" | "failed" | "timeout";
  message: string | null;
  finished: boolean;
};

/**
 * The api's answer for the session's latest run (GET /runs/{id}), read for a tab
 * that was not there when the run ended. Without this, a reload said the PoC had
 * never been run while its result and downloads were still on the server. An
 * answer that says nothing usable leaves the tab as it was.
 */
export function restoredRun(body: unknown): RestoredRun | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  const phase = b.phase;
  if (phase === "pending" || phase === "running") {
    if (b.finished === true) return null;
    return { phase: "running", message: null, finished: false };
  }
  if (phase === "succeeded" || phase === "failed" || phase === "timeout") {
    return {
      phase,
      message: runEndMessage({ phase, reason: b.reason, message: b.message }),
      finished: true,
    };
  }
  return null;
}
