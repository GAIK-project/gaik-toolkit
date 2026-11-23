"use client";

import { useState } from "react";
import { pathBelowField, type TracedSource, type TraceVerdict } from "@/lib/poc-source-trace";
import { Icon, type IconName } from "./icons";

export type SourceLabels = {
  /** Accessible name of a value's list of sources. */
  label: string;
  /** "p. {n}" */
  page: string;
  /** "Show the other {n}" */
  more: string;
  verdicts: Record<TraceVerdict, string>;
};

const MARK: Record<TraceVerdict, { icon: IconName; tone: string }> = {
  verified: { icon: "circleCheck", tone: "text-success-text" },
  check: { icon: "circleAlert", tone: "text-warning-text" },
  reworded: { icon: "info", tone: "text-text-secondary" },
  unchecked: { icon: "circle", tone: "text-text-muted" },
};

/** A list field can cite a snippet per cell; the first few say enough. */
const SHOWN = 4;

/**
 * Where a value of the run's result comes from: the snippets of the source the
 * model gave as evidence, each with the check's verdict. Under the value, so
 * the reader sees the claim and its ground together.
 */
export function FieldSources({ sources, labels }: { sources: TracedSource[]; labels: SourceLabels }) {
  const [all, setAll] = useState(false);
  if (sources.length === 0) return null;
  const shown = all ? sources : sources.slice(0, SHOWN);
  return (
    <ul
      aria-label={labels.label}
      data-testid="poc-field-sources"
      className="mt-1 flex flex-col gap-0.5 border-l-2 border-border pl-2.5 text-xs leading-relaxed text-text-secondary"
    >
      {shown.map((source, i) => {
        const mark = MARK[source.verdict];
        const below = pathBelowField(source.field);
        return (
          <li key={i} className="flex items-start gap-1.5" data-verdict={source.verdict}>
            <span className={`mt-[3px] shrink-0 ${mark.tone}`} title={labels.verdicts[source.verdict]}>
              <Icon name={mark.icon} size={12} />
              <span className="sr-only">{labels.verdicts[source.verdict]}: </span>
            </span>
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {below && <span className="mr-1.5 font-mono text-[11px] text-text-muted">{below}</span>}
              <q className="italic">{source.quote}</q>
              {source.page !== null && (
                <span className="ml-1.5 whitespace-nowrap text-text-muted">
                  {labels.page.replace("{n}", String(source.page))}
                  {source.document ? ` · ${source.document}` : ""}
                </span>
              )}
            </span>
          </li>
        );
      })}
      {!all && sources.length > SHOWN && (
        <li>
          <button
            type="button"
            onClick={() => setAll(true)}
            className="rounded font-medium text-brand-text underline-offset-2 hover:underline"
          >
            {labels.more.replace("{n}", String(sources.length - SHOWN))}
          </button>
        </li>
      )}
    </ul>
  );
}
