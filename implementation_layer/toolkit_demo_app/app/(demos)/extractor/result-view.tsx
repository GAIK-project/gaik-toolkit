"use client";

import type { ExtraTab } from "@/components/demo/schema-views";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, formatFieldName } from "@/lib/utils";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ChevronDown,
  Copy,
  Download,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import toast from "react-hot-toast";
import type { VerificationEntry } from "@/components/demo/vision-settings";
import {
  cellText,
  columnsOf,
  countFound,
  isEmptyValue,
  isRecord,
} from "./extractor-data";

function NotFound() {
  return (
    <span className="text-muted-foreground text-sm italic">not found</span>
  );
}

const isRecordList = (value: unknown): value is Record<string, unknown>[] =>
  Array.isArray(value) && value.length > 0 && value.every(isRecord);

/** A value that is not a list of records: text, a short list, or a nested record. */
function Value({ value }: { value: unknown }) {
  if (isEmptyValue(value)) return <NotFound />;

  if (Array.isArray(value)) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {value.map((item, index) => (
          <Badge key={index} variant="secondary" className="font-normal">
            {cellText(item)}
          </Badge>
        ))}
      </div>
    );
  }

  if (isRecord(value)) {
    return (
      <dl className="divide-y rounded-md border">
        {Object.entries(value).map(([key, inner]) => (
          <div key={key} className="grid gap-1 p-2 sm:grid-cols-[9rem_1fr]">
            <dt className="text-muted-foreground text-sm">
              {formatFieldName(key)}
            </dt>
            <dd>
              {isRecordList(inner) ? (
                <RowsTable rows={inner} />
              ) : (
                <Value value={inner} />
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return <span className="text-sm whitespace-pre-wrap">{String(value)}</span>;
}

/** Numbers sort as numbers, other values as text. */
function compare(a: unknown, b: unknown): number {
  const x = cellText(a);
  const y = cellText(b);
  const nx = Number(x);
  const ny = Number(y);
  if (x !== "" && y !== "" && !Number.isNaN(nx) && !Number.isNaN(ny))
    return nx - ny;
  return x.localeCompare(y);
}

/** A list of records as a table: click a heading to sort. */
function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = columnsOf(rows);
  const [sort, setSort] = useState<{ column: string; down: boolean } | null>(
    null,
  );
  const shown = sort
    ? [...rows].sort(
        (a, b) =>
          compare(a[sort.column], b[sort.column]) * (sort.down ? -1 : 1),
      )
    : rows;

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="bg-muted/50 text-xs tracking-wider uppercase">
            {columns.map((column) => (
              <th
                key={column}
                className="px-3 py-2 font-medium whitespace-nowrap"
                aria-sort={
                  sort?.column === column
                    ? sort.down
                      ? "descending"
                      : "ascending"
                    : "none"
                }
              >
                <button
                  type="button"
                  className="hover:text-primary inline-flex items-center gap-1 uppercase"
                  onClick={() =>
                    setSort(
                      sort?.column === column
                        ? sort.down
                          ? null
                          : { column, down: true }
                        : { column, down: false },
                    )
                  }
                >
                  {formatFieldName(column)}
                  {sort?.column === column ? (
                    sort.down ? (
                      <ArrowDown className="size-3" />
                    ) : (
                      <ArrowUp className="size-3" />
                    )
                  ) : (
                    <ArrowUpDown className="size-3 opacity-40" />
                  )}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, index) => (
            <tr key={index} className="hover:bg-muted/30 border-t align-top">
              {columns.map((column) => (
                <td key={column} className="px-3 py-2">
                  {isEmptyValue(row[column]) ? (
                    <NotFound />
                  ) : (
                    cellText(row[column])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type Verification = Record<
  string,
  VerificationEntry | VerificationEntry[]
>;

/** How sure the model says it is: green from 90 %, amber from 70 %, else red. */
function Confidence({
  score,
  reason,
}: {
  score: number | undefined;
  reason?: string;
}) {
  if (score === undefined) return null;
  const percent = Math.round(score * 100);
  return (
    <span
      title={reason}
      className={cn(
        "rounded px-1.5 py-0.5 font-mono text-xs font-normal",
        score >= 0.9
          ? "bg-emerald-100 text-emerald-800"
          : score >= 0.7
            ? "bg-amber-100 text-amber-800"
            : "bg-red-100 text-red-800",
      )}
    >
      {percent}%
    </span>
  );
}

function averageScore(entries: VerificationEntry[]): number | undefined {
  const scores = entries
    .map((entry) => entry.confidence_score)
    .filter((score): score is number => typeof score === "number");
  return scores.length
    ? scores.reduce((sum, score) => sum + score, 0) / scores.length
    : undefined;
}

/** One list of records, as a section that can be folded away. */
function ListSection({
  name,
  rows,
  verification,
}: {
  name: string;
  rows: Record<string, unknown>[];
  verification?: VerificationEntry | VerificationEntry[];
}) {
  const [open, setOpen] = useState(true);
  return (
    <section className="space-y-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 text-left"
      >
        <ChevronDown
          className={cn("size-4 transition-transform", !open && "-rotate-90")}
        />
        <h4 className="text-sm font-semibold">{formatFieldName(name)}</h4>
        <Badge variant="secondary" className="font-normal">
          {rows.length} {rows.length === 1 ? "row" : "rows"}
        </Badge>
        {Array.isArray(verification) && (
          <span className="text-muted-foreground flex items-center gap-1 text-xs">
            average confidence
            <Confidence score={averageScore(verification)} />
          </span>
        )}
      </button>
      {open && <RowsTable rows={rows} />}
    </section>
  );
}

function download(name: string, text: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: "application/json;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** What the extraction returned: every field of every record, also those with no value. */
export function ResultView({
  results,
  documentCount,
  seconds,
  verification,
  detail,
  noun = "document",
  extraTabs = [],
  children,
}: {
  results: Record<string, unknown>[];
  documentCount: number;
  seconds: number | null;
  /** Per field: how sure the model is of the value. */
  verification?: Verification | null;
  /** Extra text under the heading, for example the model used. */
  detail?: string;
  /** What the data was read from, in the heading: "document" or "recording". */
  noun?: string;
  /** More tabs after Readable and JSON, for example the schema the data was extracted with. */
  extraTabs?: ExtraTab[];
  /** Shown under the summary bar, for example the token usage. */
  children?: ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const [hideEmpty, setHideEmpty] = useState(false);
  const json = JSON.stringify(results, null, 2);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-card flex flex-wrap items-center gap-3 rounded-xl border p-4 shadow-sm">
        <span className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-lg">
          <Check className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            Extracted from {documentCount} {noun}
            {documentCount === 1 ? "" : "s"}
          </p>
          {seconds !== null && (
            <p className="text-muted-foreground text-xs">
              in {seconds.toFixed(1)} s{detail ? ` · ${detail}` : ""}
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          Copy JSON
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => download("extracted-data.json", json)}
        >
          <Download className="size-4" />
          Download JSON
        </Button>
      </div>

      {children}

      {results.length === 0 && (
        <p className="text-muted-foreground text-sm">No data extracted</p>
      )}

      {results.length > 0 && (
        <Tabs defaultValue="readable">
          <div className="flex flex-wrap items-center gap-3">
            <TabsList>
              <TabsTrigger value="readable">Readable</TabsTrigger>
              <TabsTrigger value="json">JSON</TabsTrigger>
              {extraTabs.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
            <label className="text-muted-foreground ml-auto flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={hideEmpty}
                onChange={(e) => setHideEmpty(e.target.checked)}
                className="accent-primary size-4"
              />
              Hide fields with no value
            </label>
          </div>

          <TabsContent value="readable" className="space-y-4 pt-3">
            {results.map((record, index) => {
              const { found, total } = countFound(record);
              const entries = Object.entries(record);
              const lists = entries.filter(([, value]) => isRecordList(value));
              const plain = entries.filter(
                ([, value]) =>
                  !isRecordList(value) && !(hideEmpty && isEmptyValue(value)),
              );
              return (
                <Card key={index} className="overflow-hidden shadow-sm">
                  <CardHeader className="bg-muted/40 flex flex-row items-center gap-2 space-y-0 border-b px-5 py-3">
                    <CardTitle className="text-base">
                      {results.length > 1
                        ? `Result ${index + 1}`
                        : "Extracted data"}
                    </CardTitle>
                    <span className="text-muted-foreground ml-auto text-xs">
                      {found} of {total} fields found
                    </span>
                  </CardHeader>
                  <CardContent className="space-y-5 p-5">
                    {plain.length > 0 && (
                      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        {plain.map(([key, value]) => {
                          const wide = isRecord(value) || Array.isArray(value);
                          const check = verification?.[key];
                          const single =
                            check && !Array.isArray(check) ? check : null;
                          return (
                            <div
                              key={key}
                              className={cn(
                                "min-w-0 space-y-1 rounded-lg border p-3",
                                isEmptyValue(value) && "border-dashed",
                                wide && "sm:col-span-2 xl:col-span-3",
                              )}
                            >
                              <dt className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
                                {formatFieldName(key)}
                                {single && (
                                  <Confidence
                                    score={single.confidence_score}
                                    reason={single.confidence_reason}
                                  />
                                )}
                              </dt>
                              <dd className="font-medium break-words">
                                <Value value={value} />
                              </dd>
                              {single?.confidence_reason && (
                                <p className="text-muted-foreground text-xs font-normal">
                                  {single.confidence_reason}
                                </p>
                              )}
                            </div>
                          );
                        })}
                      </dl>
                    )}
                    {lists.map(([key, value]) => (
                      <ListSection
                        key={key}
                        name={key}
                        rows={value as Record<string, unknown>[]}
                        verification={verification?.[key]}
                      />
                    ))}
                  </CardContent>
                </Card>
              );
            })}
          </TabsContent>

          <TabsContent value="json" className="pt-3">
            <pre className="bg-muted/40 max-h-[32rem] overflow-auto rounded-lg border p-4 text-xs">
              <code>{json}</code>
            </pre>
          </TabsContent>

          {extraTabs.map((tab) => (
            <TabsContent key={tab.value} value={tab.value} className="pt-3">
              {tab.content}
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
