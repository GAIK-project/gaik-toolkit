"use client";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  Check,
  Copy,
  Download,
  PenLine,
  RefreshCw,
  Search,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import type { ExtractionConfig } from "./config";
import { splitAround, unwrapRecords, valueStrings } from "./format";
import { sourceTextOf, type ExtractionResult } from "./use-extraction-pipeline";

type Highlight = { text: string; n: number };

/** The source text, with the value the user picked marked. */
function SourcePanel({
  source,
  highlight,
  onRerun,
  busy,
}: {
  source: string;
  highlight: Highlight | null;
  onRerun?: (text: string) => void;
  busy: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(source);
  const markRef = useRef<HTMLElement>(null);
  const parts = highlight ? splitAround(source, highlight.text) : null;

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [highlight]);

  if (editing) {
    return (
      <div className="space-y-2">
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={12}
          className="text-sm"
          aria-label="Edit the source text"
        />
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            disabled={busy || !draft.trim()}
            onClick={() => {
              setEditing(false);
              onRerun?.(draft);
            }}
          >
            <RefreshCw className="size-4" />
            Extract again
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="bg-muted/30 max-h-80 overflow-auto rounded-lg border p-3 text-sm leading-6 whitespace-pre-wrap">
        {parts ? (
          <>
            {parts[0]}
            <mark
              ref={markRef}
              className="rounded bg-yellow-200 px-0.5 text-yellow-950"
            >
              {parts[1]}
            </mark>
            {parts[2]}
          </>
        ) : (
          source
        )}
      </div>
      {highlight && !parts && (
        <p className="text-muted-foreground text-xs">
          This value is not quoted word for word. The model interpreted it from
          the report.
        </p>
      )}
      {onRerun && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            setDraft(source);
            setEditing(true);
          }}
        >
          <PenLine className="size-4" />
          Edit the text and extract again
        </Button>
      )}
    </div>
  );
}

/** A value, or the items of a list, each of which can be located in the source. */
export function ValueView({
  value,
  active,
  onPick,
}: {
  value: unknown;
  active: string | null;
  onPick: (text: string) => void;
}) {
  const pieces = valueStrings(value);
  const isList = Array.isArray(value);
  return (
    <div className={cn("flex flex-wrap gap-1.5", !isList && "block")}>
      {pieces.map((piece, index) => (
        <button
          key={`${piece}-${index}`}
          type="button"
          onClick={() => onPick(piece)}
          title="Show where this comes from in the source"
          className={cn(
            "hover:border-primary/60 hover:bg-primary/5 rounded-md border border-transparent text-left text-sm transition-colors",
            isList ? "bg-muted/60 px-2 py-0.5" : "-mx-1 px-1 py-0.5 leading-6",
            active === piece && "border-primary bg-primary/10",
          )}
        >
          {piece}
        </button>
      ))}
    </div>
  );
}

/** Shown for a field the report did not mention (null or empty in the output). */
export function NotFound({ label }: { label?: string }) {
  return (
    <span className="text-muted-foreground text-sm italic">
      {label ? `${label}: ` : ""}not found
    </span>
  );
}

/** What came out of a run: the records, where each value comes from, and the report. */
export function ExtractionResults({
  config,
  result,
  seconds,
  onRerun,
  busy,
}: {
  config: ExtractionConfig;
  result: ExtractionResult;
  seconds: number | null;
  /** Called with edited source text; runs the extraction again with the same settings. */
  onRerun?: (text: string) => void;
  busy: boolean;
}) {
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [copied, setCopied] = useState(false);
  const records = unwrapRecords(result.extracted_data ?? []);
  const { RecordCard } = config;
  const source = sourceTextOf(result);
  const pdfUrl = result.pdf_available
    ? `/api/pipeline/pdf/${result.job_id}`
    : null;
  const hasTranscript = Boolean(
    result.raw_transcript || result.enhanced_transcript,
  );

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(records, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  const pick = (text: string) =>
    setHighlight((current) => ({ text, n: (current?.n ?? 0) + 1 }));

  return (
    <div className="space-y-4">
      <div className="bg-card flex flex-wrap items-center gap-3 rounded-xl border p-4 shadow-sm">
        <span className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-lg">
          <Check className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {records.length === 1
              ? `1 ${config.recordNoun} extracted`
              : `${records.length} ${config.recordsNoun} extracted`}
          </p>
          {seconds !== null && (
            <p className="text-muted-foreground text-xs">
              in {seconds.toFixed(1)} s
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={copyJson}>
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          Copy JSON
        </Button>
      </div>

      <Tabs defaultValue="result">
        <TabsList>
          <TabsTrigger value="result">Result</TabsTrigger>
          {hasTranscript && (
            <TabsTrigger value="transcript">Transcript</TabsTrigger>
          )}
          {pdfUrl && <TabsTrigger value="report">Report (PDF)</TabsTrigger>}
        </TabsList>

        <TabsContent value="result" className="pt-4">
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
            <div className="space-y-4">
              {records.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Nothing was found in the text.
                </p>
              )}
              {records.map((report, index) => (
                <RecordCard
                  key={index}
                  report={report}
                  index={index}
                  total={records.length}
                  active={highlight?.text ?? null}
                  onPick={pick}
                />
              ))}
            </div>
            {source && (
              <aside className="space-y-2 lg:sticky lg:top-24">
                <h4 className="flex items-center gap-2 text-sm font-semibold">
                  <Search className="text-primary size-4" />
                  Source
                </h4>
                <p className="text-muted-foreground text-xs">
                  Click a value to see where it comes from.
                </p>
                <SourcePanel
                  source={source}
                  highlight={highlight}
                  onRerun={onRerun}
                  busy={busy}
                />
              </aside>
            )}
          </div>
        </TabsContent>

        {hasTranscript && (
          <TabsContent value="transcript" className="pt-4">
            <Tabs
              defaultValue={result.enhanced_transcript ? "enhanced" : "raw"}
            >
              <TabsList>
                {result.enhanced_transcript && (
                  <TabsTrigger value="enhanced">Enhanced</TabsTrigger>
                )}
                <TabsTrigger value="raw">Raw</TabsTrigger>
              </TabsList>
              {result.enhanced_transcript && (
                <TabsContent value="enhanced" className="pt-3">
                  <p className="bg-muted/30 rounded-lg border p-3 text-sm leading-6 whitespace-pre-wrap">
                    {result.enhanced_transcript}
                  </p>
                </TabsContent>
              )}
              <TabsContent value="raw" className="pt-3">
                <p className="bg-muted/30 rounded-lg border p-3 text-sm leading-6 whitespace-pre-wrap">
                  {result.raw_transcript}
                </p>
              </TabsContent>
            </Tabs>
          </TabsContent>
        )}

        {pdfUrl && (
          <TabsContent value="report" className="space-y-3 pt-4">
            <div className="h-[520px] overflow-hidden rounded-lg border bg-white">
              <iframe
                title={`${config.pdfTitle} PDF`}
                src={`${pdfUrl}?inline=true#toolbar=0`}
                className="size-full"
              />
            </div>
            <Button
              variant="outline"
              onClick={() => window.open(pdfUrl, "_blank")}
            >
              <Download className="size-4" />
              Download the PDF
            </Button>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
