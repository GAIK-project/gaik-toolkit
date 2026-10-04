"use client";

import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { useVisionModels } from "@/components/demo/vision-settings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { BookOpen, Loader2, Users } from "lucide-react";
import posthog from "posthog-js";
import { useState } from "react";
import toast from "react-hot-toast";
import {
  agreementText,
  EXPECTATION_TEXT,
  majority,
  median,
  meets,
  PAIR_EXAMPLES,
  type Severity,
} from "./judge-data";
import {
  ExampleCard,
  ExpectationLine,
  RawJson,
  ScoreMeter,
  ScoringGuide,
  SeverityBadge,
  UsageBar,
  readJudgeError,
  useJudgeSubmit,
  type Usage,
} from "./judge-shared";

const JUDGE_DOCS_URL =
  "https://gaik-project.github.io/gaik-toolkit/toolkit/evals/llm-judge/";
const PANEL_SIZE = 3;

interface PanelEntry {
  provider: string;
  equivalent?: boolean;
  severity?: Severity;
  score?: number;
  reason?: string;
  usage?: Usage | null;
  error?: string;
}

export interface PanelResult {
  per_judge: PanelEntry[];
  skipped: { provider: string; reason: string }[];
  agreement_score: number;
  total_cost_usd: number;
  total_duration_s: number;
}

const SEVERITY_BAR: Record<Severity, string> = {
  ok: "bg-emerald-500",
  suspect: "bg-amber-500",
  wrong: "bg-rose-500",
};

export function PanelTab() {
  const catalogue = useVisionModels();
  // The judges are the first models the server offers: its own model first. No model is named here.
  const judges = catalogue.choices.openai.slice(0, PANEL_SIZE);

  const [exampleId, setExampleId] = useState<string | null>(null);
  const [expected, setExpected] = useState("");
  const [extracted, setExtracted] = useState("");
  const [fieldName, setFieldName] = useState("");
  const { isLoading, result, setResult, run } = useJudgeSubmit<PanelResult>();

  const example = PAIR_EXAMPLES.find((entry) => entry.id === exampleId) ?? null;

  function pick(id: string) {
    const next = PAIR_EXAMPLES.find((entry) => entry.id === id);
    if (!next) return;
    setExampleId(id);
    setExpected(next.expected);
    setExtracted(next.extracted);
    setFieldName(next.fieldName);
    setResult(null);
  }

  async function handleSubmit() {
    if (!extracted.trim() || !expected.trim()) {
      toast.error("Please fill in both texts");
      return;
    }
    if (judges.length < 2) {
      toast.error("The server offers fewer than two models for a panel");
      return;
    }
    await run(async (signal) => {
      const response = await apiFetch("/api/llm-judge/panel/text-pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extracted_text: extracted,
          expected_text: expected,
          field_name: fieldName || undefined,
          judges: judges.map((model) => ({ provider: "openai", model })),
        }),
        signal,
      });
      if (!response.ok)
        throw new Error(await readJudgeError(response, "Panel call failed"));
      const data = (await response.json()) as PanelResult;
      posthog.capture("llm_judge_run", {
        tab: "panel",
        provider: "panel",
        example: exampleId,
      });
      return data;
    });
  }

  const answered = result?.per_judge.filter(
    (entry): entry is PanelEntry & { severity: Severity } =>
      Boolean(entry.severity),
  );
  const verdict = answered
    ? majority(answered.map((entry) => entry.severity))
    : null;
  const counts = answered?.reduce<Record<Severity, number>>(
    (sum, entry) => ({ ...sum, [entry.severity]: sum[entry.severity] + 1 }),
    { ok: 0, suspect: 0, wrong: 0 },
  );

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Start from a case</h2>
        <div
          role="radiogroup"
          aria-label="Panel cases"
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
        >
          {PAIR_EXAMPLES.map((entry) => (
            <ExampleCard
              key={entry.id}
              title={entry.title}
              summary={entry.summary}
              tag={EXPECTATION_TEXT[entry.expect]}
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
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1.5">
                <CardTitle>1. The two texts</CardTitle>
                <CardDescription>
                  The same pair goes to every judge one after another, and the
                  panel reports how often they agree. Several models cancel out
                  the quirks of any single one.
                </CardDescription>
              </div>
              <Button asChild variant="ghost" size="sm" className="shrink-0">
                <a
                  href={JUDGE_DOCS_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="gap-1"
                >
                  <BookOpen className="h-3.5 w-3.5" />
                  How it works
                </a>
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="bg-muted/40 flex flex-wrap items-center gap-2 rounded-md border p-3 text-xs">
              <span className="text-muted-foreground">
                The judges are the server&apos;s models:
              </span>
              {judges.length === 0 ? (
                <span className="text-muted-foreground">loading…</span>
              ) : (
                judges.map((model) => (
                  <Badge key={model} variant="secondary" className="font-mono">
                    {model}
                  </Badge>
                ))
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="panel-expected">Reference</Label>
              <Textarea
                id="panel-expected"
                rows={3}
                value={expected}
                onChange={(e) => {
                  setExpected(e.target.value);
                  setExampleId(null);
                }}
                placeholder="Reference text…"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="panel-extracted">Candidate</Label>
              <Textarea
                id="panel-extracted"
                rows={3}
                value={extracted}
                onChange={(e) => {
                  setExtracted(e.target.value);
                  setExampleId(null);
                }}
                placeholder="Candidate text…"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="panel-field">Field name (optional)</Label>
              <Input
                id="panel-field"
                value={fieldName}
                onChange={(e) => setFieldName(e.target.value)}
                placeholder="e.g. incident_summary"
                disabled={isLoading}
              />
            </div>
            <Button
              onClick={handleSubmit}
              disabled={
                isLoading ||
                judges.length < 2 ||
                !expected.trim() ||
                !extracted.trim()
              }
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Running the panel…
                </>
              ) : (
                <>
                  <Users className="mr-2 h-4 w-4" />
                  Run the judge panel
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4" aria-live="polite">
          {isLoading && (
            <LoadingCard
              message={`${judges.length} judges, one after another…`}
              subMessage="The time is the sum of the judges"
            />
          )}
          {result && !isLoading && answered && counts && (
            <Card>
              <CardHeader>
                <CardTitle>
                  Panel: {(result.agreement_score * 100).toFixed(0)}% agreement
                </CardTitle>
                <CardDescription>
                  Total ${result.total_cost_usd.toFixed(4)} ·{" "}
                  {result.total_duration_s.toFixed(2)}s
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="bg-muted/40 space-y-2 rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-muted-foreground text-xs">
                      Panel verdict:
                    </span>
                    {verdict && <SeverityBadge severity={verdict} />}
                    {median(answered.map((entry) => entry.score ?? 0)) !==
                      null && (
                      <ScoreMeter
                        score={
                          median(answered.map((entry) => entry.score ?? 0)) ??
                          undefined
                        }
                      />
                    )}
                  </div>
                  <div
                    className="flex h-2.5 overflow-hidden rounded-full"
                    role="img"
                    aria-label={`${counts.ok} ok, ${counts.suspect} suspect, ${counts.wrong} wrong`}
                  >
                    {(["ok", "suspect", "wrong"] as const).map((severity) =>
                      counts[severity] > 0 ? (
                        <span
                          key={severity}
                          className={SEVERITY_BAR[severity]}
                          style={{
                            width: `${(counts[severity] / answered.length) * 100}%`,
                          }}
                        />
                      ) : null,
                    )}
                  </div>
                  <p className="text-muted-foreground text-xs">
                    {counts.ok} ok · {counts.suspect} suspect · {counts.wrong}{" "}
                    wrong. {agreementText(result.agreement_score)}
                    {result.agreement_score < 0.99 &&
                      " When judges split, the panel shows the harshest verdict, so a problem is never lost."}
                  </p>
                </div>

                {example &&
                  verdict &&
                  expected === example.expected &&
                  extracted === example.extracted && (
                    <ExpectationLine
                      met={meets(example.expect, verdict)}
                      expectedText={EXPECTATION_TEXT[example.expect]}
                    />
                  )}

                <div className="grid gap-3 sm:grid-cols-2">
                  {result.per_judge.map((entry) => (
                    <div
                      key={entry.provider}
                      className={cn(
                        "space-y-2 rounded-md border p-3",
                        entry.severity &&
                          verdict &&
                          entry.severity !== verdict &&
                          "border-dashed",
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="font-mono">
                          {entry.provider}
                        </Badge>
                        {entry.severity && (
                          <SeverityBadge severity={entry.severity} />
                        )}
                        <ScoreMeter score={entry.score} />
                      </div>
                      {entry.reason && (
                        <p className="text-muted-foreground text-sm">
                          {entry.reason}
                        </p>
                      )}
                      {entry.error && (
                        <p className="text-destructive text-sm">
                          {entry.error}
                        </p>
                      )}
                      {entry.usage && (
                        <p className="text-muted-foreground font-mono text-xs">
                          {entry.usage.duration_s?.toFixed(2)}s · $
                          {entry.usage.cost_usd?.toFixed(4)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
                {answered.some((entry) => entry.severity !== verdict) && (
                  <p className="text-muted-foreground text-xs">
                    A dashed card is a judge that disagreed with the panel
                    verdict.
                  </p>
                )}

                {result.skipped.length > 0 && (
                  <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
                    <p className="mb-1 text-xs font-medium text-amber-700">
                      Skipped judges
                    </p>
                    {result.skipped.map((entry) => (
                      <p
                        key={entry.provider}
                        className="text-muted-foreground text-xs"
                      >
                        <span className="font-mono">{entry.provider}</span>:{" "}
                        {entry.reason}
                      </p>
                    ))}
                  </div>
                )}
                <UsageBar usage={null} />
                <RawJson data={result} label="Raw panel response" />
              </CardContent>
            </Card>
          )}
          {!result && !isLoading && (
            <EmptyStateCard
              icon={Users}
              title="No panel run yet"
              description="Pick a case or fill in both texts, then run all the judges."
            />
          )}
          <ScoringGuide />
        </div>
      </div>
    </div>
  );
}
