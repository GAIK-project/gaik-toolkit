"use client";

import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Gavel, Loader2, ScrollText } from "lucide-react";
import posthog from "posthog-js";
import { useMemo, useState } from "react";
import toast from "react-hot-toast";
import { findQuote } from "../knowledge-curator/curator-data";
import {
  fieldRows,
  HALLUCINATION_EXAMPLES,
  outcomeOf,
  type FieldRow,
  type Severity,
} from "./judge-data";
import {
  ExampleCard,
  ExpectationLine,
  RawJson,
  SeverityBadge,
  UsageBar,
  readJudgeError,
  useJudgeSubmit,
  type Usage,
} from "./judge-shared";

const DEMO_PROVIDER = "openai";

interface Flag {
  field: string;
  value: string;
  severity: Severity;
  reason: string;
}

export interface HallucinationResult {
  flags: Flag[];
  raw_judge_text: string;
  usage: Usage | null;
}

interface Judged {
  source: string;
  extracted: Record<string, unknown>;
}

/** The source text with each supported value marked where it occurs. */
function SourceView({
  source,
  rows,
  selected,
  onSelect,
}: {
  source: string;
  rows: FieldRow[];
  selected: string | null;
  onSelect: (field: string) => void;
}) {
  const marks = rows
    .filter((row) => row.status === "supported")
    .flatMap((row) => {
      const found = findQuote(source, row.value);
      return found ? [{ ...found, field: row.field }] : [];
    })
    .sort((a, b) => a.start - b.start)
    .filter(
      (mark, index, all) => index === 0 || mark.start >= all[index - 1].end,
    );

  const pieces: React.ReactNode[] = [];
  let at = 0;
  for (const mark of marks) {
    pieces.push(source.slice(at, mark.start));
    pieces.push(
      <mark
        key={mark.field}
        onClick={() => onSelect(mark.field)}
        title={mark.field}
        className={cn(
          "cursor-pointer rounded px-0.5 text-inherit",
          selected === mark.field
            ? "bg-emerald-300 ring-2 ring-emerald-600"
            : "bg-emerald-100 hover:bg-emerald-200",
        )}
      >
        {source.slice(mark.start, mark.end)}
      </mark>,
    );
    at = mark.end;
  }
  pieces.push(source.slice(at));
  return (
    <p className="bg-muted/30 rounded-md border p-3 text-sm leading-relaxed whitespace-pre-wrap">
      {pieces}
    </p>
  );
}

export function HallucinationsTab() {
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [sourceText, setSourceText] = useState("");
  const [extracted, setExtracted] = useState("");
  const [judged, setJudged] = useState<Judged | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const { isLoading, result, setResult, run } =
    useJudgeSubmit<HallucinationResult>();

  const example =
    HALLUCINATION_EXAMPLES.find((entry) => entry.id === exampleId) ?? null;

  function pick(id: string) {
    const next = HALLUCINATION_EXAMPLES.find((entry) => entry.id === id);
    if (!next) return;
    setExampleId(id);
    setSourceText(next.source);
    setExtracted(JSON.stringify(next.extracted, null, 2));
    setResult(null);
    setJudged(null);
  }

  async function handleSubmit() {
    if (!sourceText.trim()) {
      toast.error("Source text is required");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(extracted);
    } catch (e) {
      toast.error(
        `Invalid JSON: ${e instanceof Error ? e.message : "parse error"}`,
      );
      return;
    }
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      toast.error("Extracted must be a JSON object");
      return;
    }
    await run(async (signal) => {
      const response = await apiFetch("/api/llm-judge/hallucinations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_text: sourceText,
          extracted: parsed,
          provider: DEMO_PROVIDER,
        }),
        signal,
      });
      if (!response.ok)
        throw new Error(await readJudgeError(response, "Judge call failed"));
      const data = (await response.json()) as HallucinationResult;
      posthog.capture("llm_judge_run", {
        tab: "hallucinations",
        provider: DEMO_PROVIDER,
        example: exampleId,
      });
      setJudged({
        source: sourceText,
        extracted: parsed as Record<string, unknown>,
      });
      setSelected(null);
      return data;
    });
  }

  const rows = useMemo(
    () => (result && judged ? fieldRows(judged.extracted, result.flags) : []),
    [result, judged],
  );
  const flagged = rows.filter((row) => row.status !== "supported");
  const outcome =
    example && result && judged && sourceText === example.source
      ? outcomeOf(
          result.flags.map((flag) => flag.field),
          example.invented,
        )
      : null;

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Start from a case</h2>
        <div
          role="radiogroup"
          aria-label="Hallucination cases"
          className="grid gap-3 sm:grid-cols-2"
        >
          {HALLUCINATION_EXAMPLES.map((entry) => (
            <ExampleCard
              key={entry.id}
              title={entry.title}
              summary={entry.summary}
              tag={
                entry.invented.length > 0
                  ? `${entry.invented.length} invented fields`
                  : "nothing invented"
              }
              selected={exampleId === entry.id}
              disabled={isLoading}
              onClick={() => pick(entry.id)}
            />
          ))}
        </div>
      </section>

      <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>1. The source and the extraction</CardTitle>
            <CardDescription>
              Paste a source text and the extractor&apos;s output. The judge
              flags any field whose value the source does not support.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="source-text">Source text</Label>
              <Textarea
                id="source-text"
                rows={5}
                value={sourceText}
                onChange={(e) => {
                  setSourceText(e.target.value);
                  setExampleId(null);
                }}
                placeholder="The ground-truth document body (transcript, parsed text, etc.)"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extracted-json">Extracted data (JSON)</Label>
              <Textarea
                id="extracted-json"
                rows={8}
                value={extracted}
                onChange={(e) => {
                  setExtracted(e.target.value);
                  setExampleId(null);
                }}
                placeholder='{"field_a": "value", …}'
                disabled={isLoading}
                className="font-mono text-sm"
              />
              <p className="text-muted-foreground text-xs">
                Each <code>key: value</code> pair is one field. Empty fields are
                skipped.
              </p>
            </div>
            <Button
              onClick={handleSubmit}
              disabled={isLoading || !sourceText.trim() || !extracted.trim()}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Checking…
                </>
              ) : (
                <>
                  <Gavel className="mr-2 h-4 w-4" />
                  Detect hallucinations
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4" aria-live="polite">
          {isLoading && <LoadingCard message="Reviewing the fields…" />}
          {result && !isLoading && judged && (
            <Card>
              <CardHeader>
                <CardTitle>
                  {flagged.length === 0
                    ? "Every field is grounded"
                    : `${flagged.length} field${flagged.length === 1 ? "" : "s"} not supported`}
                </CardTitle>
                <CardDescription>
                  {rows.length - flagged.length} of {rows.length} fields are
                  supported by the source.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {outcome && example && (
                  <ExpectationLine
                    met={
                      outcome.missed.length === 0 && outcome.extra.length === 0
                    }
                    expectedText={
                      example.invented.length > 0
                        ? `Invented: ${example.invented.join(", ")}`
                        : "Nothing was invented"
                    }
                    detail={[
                      outcome.found.length > 0 &&
                        `found ${outcome.found.join(", ")}`,
                      outcome.missed.length > 0 &&
                        `missed ${outcome.missed.join(", ")}`,
                      outcome.extra.length > 0 &&
                        `also flagged ${outcome.extra.join(", ")}`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  />
                )}

                <ul className="divide-y rounded-md border">
                  {rows.map((row) => (
                    <li key={row.field}>
                      <button
                        type="button"
                        onClick={() =>
                          setSelected(selected === row.field ? null : row.field)
                        }
                        aria-pressed={selected === row.field}
                        className={cn(
                          "hover:bg-muted/40 flex w-full flex-col gap-1 p-3 text-left transition-colors",
                          selected === row.field && "bg-muted/50",
                        )}
                      >
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm font-medium">
                            {row.field}
                          </span>
                          <span className="text-muted-foreground font-mono text-xs break-all">
                            = {row.value}
                          </span>
                          {row.status === "supported" ? (
                            <Badge
                              variant="outline"
                              className="gap-1 border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
                            >
                              supported
                            </Badge>
                          ) : (
                            <SeverityBadge severity={row.status} />
                          )}
                        </span>
                        {row.reason && (
                          <span className="text-muted-foreground text-sm">
                            {row.reason}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>

                <div className="space-y-1">
                  <p className="text-sm font-semibold">
                    Where the source supports them
                  </p>
                  <SourceView
                    source={judged.source}
                    rows={rows}
                    selected={selected}
                    onSelect={(field) =>
                      setSelected(selected === field ? null : field)
                    }
                  />
                  <p className="text-muted-foreground text-xs">
                    Green marks show where a supported value is in the source. A
                    value that was reworded is not marked, though it can still
                    be supported. Click a field or a mark to match them.
                  </p>
                </div>
                <UsageBar usage={result.usage} />
                <RawJson data={result} />
              </CardContent>
            </Card>
          )}
          {!result && !isLoading && (
            <EmptyStateCard
              icon={ScrollText}
              title="No check yet"
              description="Pick a case, or paste a source text and an extracted JSON object, then click Detect."
            />
          )}
        </div>
      </div>
    </div>
  );
}
