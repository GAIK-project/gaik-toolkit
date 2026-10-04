"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  Copy,
  Download,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import toast from "react-hot-toast";
import { barsOf, columnsOf, sortRows, toCsv, type Row } from "./tabular-data";

export interface AskResponse {
  question: string;
  answer: string;
  succeeded: boolean;
  sql: string | null;
  reasoning: string | null;
  rows: Row[];
  row_count: number;
  attempts: number;
  error: string | null;
}

export interface Asked {
  id: number;
  response: AskResponse;
  seconds: number;
}

function save(name: string, text: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/csv;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** The rows of an answer as a table: click a heading to sort. */
function RowsTable({ rows }: { rows: Row[] }) {
  const columns = columnsOf(rows);
  const [sort, setSort] = useState<{
    column: string;
    descending: boolean;
  } | null>(null);
  const shown = useMemo(
    () => (sort ? sortRows(rows, sort.column, sort.descending) : rows),
    [rows, sort],
  );
  return (
    <div className="max-h-80 overflow-auto rounded-md border">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted sticky top-0">
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                className="px-3 py-2 font-medium"
                aria-sort={
                  sort?.column === column
                    ? sort.descending
                      ? "descending"
                      : "ascending"
                    : "none"
                }
              >
                <button
                  type="button"
                  className="hover:text-primary inline-flex items-center gap-1"
                  onClick={() =>
                    setSort(
                      sort?.column === column
                        ? sort.descending
                          ? null
                          : { column, descending: true }
                        : { column, descending: false },
                    )
                  }
                >
                  {column}
                  {sort?.column === column ? (
                    sort.descending ? (
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
            <tr key={index} className="hover:bg-muted/30 border-t">
              {columns.map((column) => (
                <td key={column} className="px-3 py-2 font-mono text-xs">
                  {row[column] === null || row[column] === undefined ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    String(row[column])
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

/** One value per label as horizontal bars. */
function Bars({ rows }: { rows: Row[] }) {
  const shape = barsOf(rows);
  if (!shape) return null;
  const max = Math.max(...shape.bars.map((bar) => Math.abs(bar.value)), 1);
  return (
    <div className="space-y-1.5">
      <p className="text-muted-foreground text-xs">
        {shape.valueColumn} by {shape.labelColumn}
      </p>
      {shape.bars.map((bar) => (
        <div key={bar.label} className="flex items-center gap-2 text-xs">
          <span className="w-36 shrink-0 truncate text-right" title={bar.label}>
            {bar.label}
          </span>
          <div className="bg-muted h-5 flex-1 overflow-hidden rounded">
            <div
              className={cn(
                "h-full rounded",
                bar.value < 0 ? "bg-rose-400" : "bg-primary/70",
              )}
              style={{ width: `${(Math.abs(bar.value) / max) * 100}%` }}
            />
          </div>
          <span className="w-20 shrink-0 font-mono">
            {Number.isInteger(bar.value) ? bar.value : bar.value.toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** What the agent answered: the answer, the SQL it ran, and the rows it got. */
export function AnswerCard({
  asked,
  onRemove,
}: {
  asked: Asked;
  onRemove: () => void;
}) {
  const { response, seconds } = asked;
  const [copied, setCopied] = useState(false);
  const hasBars = barsOf(response.rows) !== null;

  const copySql = async () => {
    try {
      await navigator.clipboard.writeText(response.sql ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <Card>
      <CardHeader className="gap-2 pb-3">
        <div className="flex flex-wrap items-start gap-2">
          <CardTitle className="min-w-0 flex-1 text-base">
            {response.question}
          </CardTitle>
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Remove this answer"
            onClick={onRemove}
          >
            <X />
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5 text-xs">
          {response.succeeded ? (
            <Badge
              variant="outline"
              className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
            >
              <Check className="size-3" />
              the query ran
            </Badge>
          ) : (
            <Badge variant="destructive">
              <AlertTriangle className="size-3" />
              the query failed
            </Badge>
          )}
          <Badge variant="outline" className="font-normal">
            {response.row_count} {response.row_count === 1 ? "row" : "rows"}
          </Badge>
          {response.attempts > 1 && (
            <Badge
              variant="outline"
              className="border-amber-500 font-normal text-amber-700"
            >
              SQL corrected: {response.attempts} attempts
            </Badge>
          )}
          <Badge variant="outline" className="font-normal">
            {seconds.toFixed(1)} s
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="answer">
          <TabsList>
            <TabsTrigger value="answer">Answer</TabsTrigger>
            <TabsTrigger value="sql" disabled={!response.sql}>
              SQL
            </TabsTrigger>
            <TabsTrigger value="rows" disabled={response.rows.length === 0}>
              Rows
              <span className="text-muted-foreground ml-1.5 text-xs">
                {response.row_count}
              </span>
            </TabsTrigger>
            {hasBars && <TabsTrigger value="chart">Chart</TabsTrigger>}
          </TabsList>

          <TabsContent value="answer" className="mt-3 space-y-3">
            {response.succeeded ? (
              <MessageResponse className="text-sm">
                {response.answer}
              </MessageResponse>
            ) : (
              <p className="text-destructive text-sm">
                {response.error ?? "The agent could not answer."}
              </p>
            )}
            {response.succeeded && response.rows.length === 0 && (
              <p className="text-muted-foreground text-sm">
                The query ran but returned no rows.
              </p>
            )}
          </TabsContent>

          <TabsContent value="sql" className="mt-3 space-y-2">
            {response.reasoning && (
              <p className="text-muted-foreground text-sm">
                <span className="text-foreground font-medium">
                  Why this query:{" "}
                </span>
                {response.reasoning}
              </p>
            )}
            <pre className="bg-muted/40 max-h-72 overflow-auto rounded-md border p-3 font-mono text-xs whitespace-pre-wrap">
              {response.sql}
            </pre>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void copySql()}
              >
                {copied ? <Check /> : <Copy />}
                Copy the SQL
              </Button>
              <span className="text-muted-foreground text-xs">
                Read-only: the agent can only read your file, never change it.
              </span>
            </div>
          </TabsContent>

          <TabsContent value="rows" className="mt-3 space-y-2">
            <RowsTable rows={response.rows} />
            <Button
              size="sm"
              variant="outline"
              onClick={() => save("answer-rows.csv", toCsv(response.rows))}
            >
              <Download />
              Download the rows (CSV)
            </Button>
          </TabsContent>

          {hasBars && (
            <TabsContent value="chart" className="mt-3">
              <Bars rows={response.rows} />
            </TabsContent>
          )}
        </Tabs>
      </CardContent>
    </Card>
  );
}
