import type { ReactNode } from "react";
import {
  type Pair,
  type ShownValue,
  type ValueWords,
  EMPTY_MARK,
  groundingFlags,
  recordsLayout,
} from "@/lib/case-value";
import { sourceRef, sourceRefPlace } from "@/lib/source-ref";
import { FileIcon } from "./file-icon";
import { Icon } from "./icons";

/**
 * What a solution produced, as a person would write it. The cases view and
 * the PoC tab's run result show the same kind of data (a record of any
 * shape), so they draw it with the same views: lib/case-value reads a value,
 * and these lay it out.
 */

export type ResultLabels = {
  /** The disclosure of a value with no plain reading. */
  showRaw: string;
  /** A source reference's page: "p. {n}". */
  page: string;
};

/**
 * A line of text. A source reference ("meeting.wav|00:00:00|00:01:12",
 * "agenda.pdf|2") reads as the file's name with its type's mark and where in
 * it; any other text is as written (lib/source-ref).
 */
function Words({ text, labels }: { text: string; labels: ResultLabels }) {
  const ref = sourceRef(text);
  if (!ref) return <span className="whitespace-pre-line [overflow-wrap:anywhere]">{text}</span>;
  return (
    <span className="[overflow-wrap:anywhere]" data-testid="source-ref">
      <FileIcon name={ref.file} size={14} className="mr-1.5 inline-block shrink-0 align-[-2px]" />
      {ref.file}
      <span className="ml-1.5 whitespace-nowrap tabular-nums text-text-muted">{sourceRefPlace(ref, labels.page)}</span>
    </span>
  );
}

/** A record's fields as "label: value" lines, where there is no room for columns. */
function PairLines({ pairs, labels }: { pairs: Pair[]; labels: ResultLabels }) {
  return (
    <ul className="space-y-0.5">
      {pairs.map((pair, i) => (
        <li key={i}>
          <span className="text-text-secondary">{pair.label}: </span>
          <ValueView shown={pair.value} labels={labels} />
        </li>
      ))}
    </ul>
  );
}

/**
 * A result value on the page, as lib/case-value read it: lines, label and
 * value pairs or records, never JSON. Only a shape with no plain reading is
 * JSON, and that is behind "Show raw".
 */
export function ValueView({ shown, labels }: { shown: ShownValue; labels: ResultLabels }) {
  switch (shown.kind) {
    case "empty":
      return <span className="text-text-muted">{EMPTY_MARK}</span>;
    case "text":
      return <Words text={shown.text} labels={labels} />;
    case "list":
      return shown.items.length === 1 ? (
        <Words text={shown.items[0]} labels={labels} />
      ) : (
        <ul className="list-disc space-y-0.5 pl-4 marker:text-text-muted [overflow-wrap:anywhere]">
          {shown.items.map((item, i) => (
            <li key={i}>
              <Words text={item} labels={labels} />
            </li>
          ))}
        </ul>
      );
    case "pairs":
      return <PairLines pairs={shown.pairs} labels={labels} />;
    case "records":
      // Records inside a value: each one's lines, parted by a little air.
      return (
        <ul className="space-y-2">
          {shown.rows.map((row, i) => (
            <li key={i}>
              <PairLines pairs={row} labels={labels} />
            </li>
          ))}
        </ul>
      );
    case "raw":
      return (
        <details className="group">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm text-text-secondary transition-colors hover:text-text [&::-webkit-details-marker]:hidden">
            <Icon name="chevronRight" size={14} className="shrink-0 transition-transform group-open:rotate-90" />
            {labels.showRaw}
          </summary>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-xs text-text-secondary [overflow-wrap:anywhere]">{shown.json}</pre>
        </details>
      );
  }
}

/**
 * A field that is a list of records. Few short fields are a table; long or
 * many fields are each record's label and value pairs, numbered and parted by
 * a rule, so a sentence gets the width of the page and not of a sixth of it.
 * `testId` names the two layouts: "{testId}-records-table" and "{testId}-records".
 */
export function RecordsView({
  shown,
  labels,
  testId,
}: {
  shown: Extract<ShownValue, { kind: "records" }>;
  labels: ResultLabels;
  testId: string;
}) {
  if (recordsLayout(shown) === "table") {
    // A heading or a short value may break inside a word: on a phone four
    // columns of long field names would otherwise push the table past its card.
    return (
      <table className="w-full text-left" data-testid={`${testId}-records-table`}>
        <thead>
          <tr className="border-b border-border-strong text-xs text-text-secondary">
            {/* By place, as the cells under them are: two fields can read alike ("unit_price", "unitPrice"). */}
            {shown.columns.map((column, i) => (
              <th key={i} scope="col" className="py-1.5 pr-3 font-medium hyphens-auto [overflow-wrap:anywhere] last:pr-0">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.rows.map((row, i) => (
            <tr key={i} className="border-b border-border align-top">
              {row.map((pair, j) => (
                <td key={j} className="py-1.5 pr-3 [overflow-wrap:anywhere] last:pr-0"><ValueView shown={pair.value} labels={labels} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <ol className="divide-y divide-border border-y border-border" data-testid={`${testId}-records`}>
      {shown.rows.map((row, i) => (
        <li key={i} className="flex gap-3 py-3">
          <span className="w-5 shrink-0 pt-px text-xs tabular-nums leading-5 text-text-muted" aria-hidden="true">{i + 1}</span>
          <dl className="min-w-0 flex-1 space-y-2">
            {row.map((pair, j) => (
              <div key={j} className="sm:grid sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-x-4">
                <dt className="text-xs text-text-secondary sm:text-sm">{pair.label}</dt>
                <dd className="min-w-0"><ValueView shown={pair.value} labels={labels} /></dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ol>
  );
}

export type ResultField = {
  /** The field's key in the record. */
  field: string;
  label: string;
  shown: ShownValue;
  /** Drawn under the value: where it comes from, say. */
  below?: ReactNode;
};

/**
 * One record's fields. A field that is a list of records gets the full width
 * under its name as a heading; any other is its label beside its value, and
 * above it on a phone.
 */
export function ResultFields({
  fields,
  labels,
  testId,
}: {
  fields: ResultField[];
  labels: ResultLabels;
  testId: string;
}) {
  return (
    <dl className="space-y-2.5 text-sm">
      {fields.map(({ field, label, shown, below }) =>
        shown.kind === "records" ? (
          <div key={field} className="pt-1.5" data-field={field}>
            <dt className="mb-1.5 font-semibold text-text">{label}</dt>
            <dd className="min-w-0">
              <RecordsView shown={shown} labels={labels} testId={testId} />
              {below}
            </dd>
          </div>
        ) : (
          <div key={field} className="sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,3fr)] sm:gap-x-3" data-field={field}>
            <dt className="text-xs font-medium text-text-secondary sm:text-sm">{label}</dt>
            <dd className="min-w-0">
              <ValueView shown={shown} labels={labels} />
              {below}
            </dd>
          </div>
        ),
      )}
    </dl>
  );
}

export type GroundingLabels = ResultLabels & {
  /** Said when the check passed. */
  ok: string;
  bad: string;
  /** What to do, under the values the check names. */
  checkThese: string;
  /** What to do when the check names no values. */
  checkResult: string;
};

/**
 * The grounding check of a result. A failed check lists the values it could
 * not find in the source, when it names them (`hallucination_flags`), and says
 * what to do with them; one that only says it failed is a single line. A
 * passed check is one line, in the cases view and on the PoC tab alike.
 * `testId` names the block, and "{testId}-flags" its list.
 */
export function GroundingNote({
  validation,
  words,
  labels,
  testId,
}: {
  validation: ({ passed?: boolean } & Record<string, unknown>) | null | undefined;
  words: ValueWords;
  labels: GroundingLabels;
  testId: string;
}) {
  if (!validation) return null;
  if (validation.passed) {
    return (
      <div className="text-sm" data-testid={testId}>
        <p className="flex items-center gap-1.5 text-success-text">
          <Icon name="circleCheck" size={15} className="shrink-0" />
          {labels.ok}
        </p>
      </div>
    );
  }
  const flags = groundingFlags(validation, words);
  return (
    <div className="text-sm" data-testid={testId}>
      <p className="text-warning-text">
        <Icon name="circleAlert" size={15} className="mr-1.5 inline-block shrink-0 align-[-2px]" />
        {labels.bad}
        {flags.length === 0 && <span className="text-text-secondary">. {labels.checkResult}</span>}
      </p>
      {flags.length > 0 && (
        <>
          <ul className="mt-2 space-y-2" data-testid={`${testId}-flags`}>
            {flags.map((flag, i) => (
              <li key={i} className="[overflow-wrap:anywhere]">
                {flag.field && <span className="font-medium text-text">{flag.field}: </span>}
                <ValueView shown={flag.value} labels={labels} />
                {flag.reason && <span className="block text-xs text-text-muted">{flag.reason}</span>}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-text-secondary">{labels.checkThese}</p>
        </>
      )}
    </div>
  );
}
