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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Loader2, Scale, Sparkles } from "lucide-react";
import posthog from "posthog-js";
import { useState } from "react";
import toast from "react-hot-toast";
import {
  EXPECTATION_TEXT,
  meets,
  PAIR_EXAMPLES,
  wordDiff,
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

// The backend resolves this to whatever credentials the deployment has.
const DEMO_PROVIDER = "openai";

export interface TextPairResult {
  equivalent: boolean;
  severity: Severity;
  score: number;
  reason: string;
  usage: Usage | null;
}

interface Past {
  id: number;
  expected: string;
  extracted: string;
  fieldName: string;
  result: TextPairResult;
}

/** The two texts with the words that differ marked: red only in the reference, green only in the candidate. */
function Diff({
  expected,
  extracted,
}: {
  expected: string;
  extracted: string;
}) {
  const parts = wordDiff(expected, extracted);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {(["expected", "extracted"] as const).map((side) => (
        <div key={side} className="space-y-1">
          <p className="text-muted-foreground text-xs font-medium">
            {side === "expected" ? "Reference" : "Candidate"}
          </p>
          <p className="rounded-md border p-3 text-sm leading-relaxed">
            {parts.map((part, index) => {
              if (part.kind === "same")
                return <span key={index}>{part.text} </span>;
              if (part.kind === "removed" && side === "expected")
                return (
                  <span key={index}>
                    <mark className="rounded bg-red-100 px-0.5 text-red-900">
                      {part.text}
                    </mark>{" "}
                  </span>
                );
              if (part.kind === "added" && side === "extracted")
                return (
                  <span key={index}>
                    <mark className="rounded bg-green-100 px-0.5 text-green-900">
                      {part.text}
                    </mark>{" "}
                  </span>
                );
              return null;
            })}
          </p>
        </div>
      ))}
    </div>
  );
}

export function TextPairTab() {
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [expected, setExpected] = useState("");
  const [extracted, setExtracted] = useState("");
  const [fieldName, setFieldName] = useState("");
  const [history, setHistory] = useState<Past[]>([]);
  // The texts the verdict is about: the boxes may be edited after it.
  const [judged, setJudged] = useState<{
    expected: string;
    extracted: string;
  } | null>(null);
  const { isLoading, result, setResult, run } =
    useJudgeSubmit<TextPairResult>();

  const example = PAIR_EXAMPLES.find((entry) => entry.id === exampleId) ?? null;

  function pick(id: string) {
    const next = PAIR_EXAMPLES.find((entry) => entry.id === id);
    if (!next) return;
    setExampleId(id);
    setExpected(next.expected);
    setExtracted(next.extracted);
    setFieldName(next.fieldName);
    setResult(null);
    setJudged(null);
  }

  async function handleSubmit() {
    if (!extracted.trim() || !expected.trim()) {
      toast.error("Please fill in both texts");
      return;
    }
    await run(async (signal) => {
      const response = await apiFetch("/api/llm-judge/text-pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extracted_text: extracted,
          expected_text: expected,
          field_name: fieldName || undefined,
          provider: DEMO_PROVIDER,
        }),
        signal,
      });
      if (!response.ok)
        throw new Error(await readJudgeError(response, "Judge call failed"));
      const data = (await response.json()) as TextPairResult;
      posthog.capture("llm_judge_run", {
        tab: "text-pair",
        provider: DEMO_PROVIDER,
        example: exampleId,
      });
      setJudged({ expected, extracted });
      setHistory((previous) =>
        [
          { id: Date.now(), expected, extracted, fieldName, result: data },
          ...previous,
        ].slice(0, 8),
      );
      return data;
    });
  }

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Start from a case</h2>
        <div
          role="radiogroup"
          aria-label="Text pair cases"
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
            <CardTitle>1. The two texts</CardTitle>
            <CardDescription>
              Compare an extractor&apos;s value with a reference. The judge
              handles paraphrasing, word forms and date formats, and needs no
              source document.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="expected">Reference (what it should be)</Label>
              <Textarea
                id="expected"
                rows={3}
                value={expected}
                onChange={(e) => {
                  setExpected(e.target.value);
                  setExampleId(null);
                }}
                placeholder="Ground-truth or reference text…"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extracted">
                Candidate (what the extractor gave)
              </Label>
              <Textarea
                id="extracted"
                rows={3}
                value={extracted}
                onChange={(e) => {
                  setExtracted(e.target.value);
                  setExampleId(null);
                }}
                placeholder="Value produced by your extractor…"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="field-name">Field name (optional)</Label>
              <Input
                id="field-name"
                value={fieldName}
                onChange={(e) => setFieldName(e.target.value)}
                placeholder="e.g. incident_summary"
                disabled={isLoading}
              />
              <p className="text-muted-foreground text-xs">
                The name helps the judge: &quot;quantity&quot; is read as a
                number, &quot;date&quot; as a date.
              </p>
            </div>
            <Button
              onClick={handleSubmit}
              disabled={isLoading || !expected.trim() || !extracted.trim()}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Judging…
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Judge equivalence
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4" aria-live="polite">
          {isLoading && <LoadingCard message="Calling the judge…" />}
          {result && !isLoading && judged && (
            <Card>
              <CardHeader>
                <CardTitle>Verdict</CardTitle>
                <CardDescription>
                  {result.equivalent
                    ? "The texts mean the same"
                    : "The texts diverge"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <SeverityBadge severity={result.severity} />
                  <ScoreMeter score={result.score} />
                  <Badge variant={result.equivalent ? "default" : "outline"}>
                    equivalent: {String(result.equivalent)}
                  </Badge>
                </div>
                {example &&
                  judged.expected === example.expected &&
                  judged.extracted === example.extracted && (
                    <ExpectationLine
                      met={meets(example.expect, result.severity)}
                      expectedText={EXPECTATION_TEXT[example.expect]}
                    />
                  )}
                <p className="text-sm leading-relaxed">{result.reason}</p>
                <div className="space-y-1">
                  <p className="text-sm font-semibold">
                    What differs word by word
                  </p>
                  <Diff
                    expected={judged.expected}
                    extracted={judged.extracted}
                  />
                  <p className="text-muted-foreground text-xs">
                    A literal comparison would call any red or green word a
                    mismatch. The judge decides whether it matters.
                  </p>
                </div>
                <UsageBar usage={result.usage} />
                <RawJson data={result} />
              </CardContent>
            </Card>
          )}
          {!result && !isLoading && (
            <EmptyStateCard
              icon={Scale}
              title="No judgement yet"
              description="Pick a case or fill in the two texts, then click Judge equivalence."
            />
          )}

          {history.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Earlier judgements</CardTitle>
                <CardDescription>
                  Click one to see its texts and verdict again.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {history.map((past) => (
                  <button
                    key={past.id}
                    type="button"
                    onClick={() => {
                      setExpected(past.expected);
                      setExtracted(past.extracted);
                      setFieldName(past.fieldName);
                      setExampleId(null);
                      setJudged({
                        expected: past.expected,
                        extracted: past.extracted,
                      });
                      setResult(past.result);
                    }}
                    className={cn(
                      "hover:bg-muted flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs transition-colors",
                      result === past.result && "border-primary bg-primary/5",
                    )}
                  >
                    <SeverityBadge severity={past.result.severity} />
                    <span className="font-mono">{past.result.score}/5</span>
                    <span className="min-w-0 flex-1 truncate">
                      {past.expected} → {past.extracted}
                    </span>
                  </button>
                ))}
              </CardContent>
            </Card>
          )}
          <ScoringGuide />
        </div>
      </div>
    </div>
  );
}
