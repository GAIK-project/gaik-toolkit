"use client";

// Where each extracted value was read. The model gives the page and a verbatim quote;
// the server finds the quote in the PDF's text layer, so the boxes drawn here come
// from the PDF, never from the model.

import { FileTypeIcon } from "@/components/demo/file-type-icon";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn, formatFieldName } from "@/lib/utils";
import { Check, CircleAlert, Minus } from "lucide-react";
import { useState } from "react";
import { cellText } from "../extractor/extractor-data";
import { TraceExplainer } from "./trace-explainer";

/**
 * The "Trace sources" option. Tracing is done by the demo around the extractor, not by
 * the extractor component: one more schema field, one more instruction, a plain check.
 */
export function TraceSourcesSwitch({
  checked,
  disabled,
  onCheckedChange,
  id = "trace-sources",
}: {
  checked: boolean;
  disabled: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5">
      <div className="space-y-0.5">
        <span className="flex items-center gap-1.5">
          <Label htmlFor={id}>Trace sources</Label>
          <TraceExplainer />
        </span>
        <p className="text-muted-foreground text-xs">
          Each value comes with its quote, highlighted in the PDF. Uses more
          output tokens.
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className="mt-0.5"
      />
    </div>
  );
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface SourceCheck {
  field: string;
  document: number;
  page: number;
  cited_page: number;
  quote: string;
  value: unknown;
  status: "found" | "moved" | "not_found" | "no_text_layer";
  value_status: "match" | "mismatch" | "unchecked";
  rects: Rect[];
  value_rects: Rect[];
}

export interface SourcesResult {
  sources: SourceCheck[];
  pages: Record<string, { image: string; width: number; height: number }>;
  documents: string[];
}

type Verdict = "ok" | "check" | "unchecked";

function verdictOf(source: SourceCheck): Verdict {
  if (source.status === "no_text_layer") return "unchecked";
  if (source.status === "not_found" || source.value_status === "mismatch")
    return "check";
  return "ok";
}

function statusText(source: SourceCheck): string {
  switch (source.status) {
    case "not_found":
      return "Check: not found in the PDF";
    case "no_text_layer":
      return "No text layer to check against";
    case "moved":
      return source.value_status === "mismatch"
        ? `Found on page ${source.page}, doesn't match the document`
        : `Found on page ${source.page}, not ${source.cited_page}`;
    default:
      return source.value_status === "mismatch"
        ? "Check: doesn't match the document"
        : "Verified";
  }
}

/** `items[2].quantity` → `Items 3 › Quantity`. */
function fieldLabel(path: string): string {
  return path
    .replace(/\[(\d+)\]/g, (_, index) => ` ${Number(index) + 1}`)
    .split(".")
    .map((part) => formatFieldName(part.trim()))
    .join(" › ");
}

const ICONS: Record<Verdict, typeof Check> = {
  ok: Check,
  check: CircleAlert,
  unchecked: Minus,
};

const ICON_STYLE: Record<Verdict, string> = {
  ok: "text-emerald-600/70",
  check: "text-amber-600",
  unchecked: "text-muted-foreground",
};

function Box({ rect, className }: { rect: Rect; className: string }) {
  return (
    <span
      aria-hidden
      className={cn("absolute rounded-[2px]", className)}
      style={{
        left: `${rect.x * 100}%`,
        top: `${rect.y * 100}%`,
        width: `${rect.w * 100}%`,
        height: `${rect.h * 100}%`,
      }}
    />
  );
}

function PageView({
  source,
  result,
}: {
  source: SourceCheck;
  result: SourcesResult;
}) {
  const page = result.pages[`${source.document}:${source.page}`];
  const name = result.documents[source.document - 1] ?? "Document";

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <FileTypeIcon name={name} />
        <span className="truncate">
          {name}, page {source.page}
        </span>
      </p>
      {page ? (
        <div className="relative overflow-hidden rounded-md border bg-white">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={page.image}
            alt={`${name}, page ${source.page}`}
            width={page.width}
            height={page.height}
            className="block h-auto w-full"
          />
          {source.rects.map((rect, index) => (
            <Box
              key={`q${index}`}
              rect={rect}
              className="bg-amber-300/30 ring-1 ring-amber-500"
            />
          ))}
          {source.value_rects.map((rect, index) => (
            <Box
              key={`v${index}`}
              rect={rect}
              className="ring-primary ring-2 ring-offset-1"
            />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground rounded-md border border-dashed p-6 text-sm">
          {source.status === "no_text_layer"
            ? "An image has no text layer, so the quote cannot be located. Read the value off the document yourself."
            : result.documents.length === 0
              ? "Checked against the text the model read. Only an uploaded PDF shows where the quote is on the page."
              : "This page is not available."}
        </p>
      )}
    </div>
  );
}

export function SourcesView({ result }: { result: SourcesResult }) {
  const order: Record<Verdict, number> = { check: 0, ok: 1, unchecked: 2 };
  const sources = [...result.sources].sort(
    (a, b) => order[verdictOf(a)] - order[verdictOf(b)],
  );
  const [selected, setSelected] = useState(0);
  const counts = sources.reduce(
    (total, source) => ({
      ...total,
      [verdictOf(source)]: total[verdictOf(source)] + 1,
    }),
    { ok: 0, check: 0, unchecked: 0 } as Record<Verdict, number>,
  );

  if (sources.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        The model returned no sources for this result.
      </p>
    );
  }

  const current = sources[Math.min(selected, sources.length - 1)];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-muted-foreground text-sm">
          {counts.check > 0 && (
            <span className="font-medium text-amber-700 dark:text-amber-500">
              {counts.check} to check,{" "}
            </span>
          )}
          {counts.ok} verified
          {counts.unchecked > 0 &&
            `, ${counts.unchecked} without a text layer to check against`}
        </p>
        <TraceExplainer label="How it works" />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <ul className="max-h-[36rem] divide-y overflow-auto rounded-md border">
          {sources.map((source, index) => {
            const verdict = verdictOf(source);
            const Icon = ICONS[verdict];
            return (
              <li key={`${source.field}-${index}`}>
                <button
                  type="button"
                  onClick={() => setSelected(index)}
                  aria-current={index === selected}
                  className={cn(
                    "hover:bg-muted/50 flex w-full gap-2.5 border-l-2 border-transparent px-3 py-2 text-left",
                    index === selected && "border-primary bg-primary/5",
                  )}
                >
                  <Icon
                    className={cn(
                      "mt-0.5 size-4 shrink-0",
                      ICON_STYLE[verdict],
                    )}
                    aria-label={statusText(source)}
                  />
                  <span className="min-w-0 flex-1 space-y-0.5">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="text-muted-foreground truncate text-xs">
                        {fieldLabel(source.field)}
                      </span>
                      <span className="truncate text-sm font-medium">
                        {cellText(source.value)}
                      </span>
                    </span>
                    <span className="text-muted-foreground block truncate text-xs">
                      “{source.quote}”
                    </span>
                    {verdict !== "ok" && (
                      <span
                        className={cn("block text-xs", ICON_STYLE[verdict])}
                      >
                        {statusText(source)}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="lg:sticky lg:top-4">
          <PageView source={current} result={result} />
        </div>
      </div>
    </div>
  );
}
