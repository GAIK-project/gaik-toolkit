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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { Check, Copy, FileText, Gavel, Loader2, Upload } from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  applySuggestions,
  gridOf,
  INVOICE_EXAMPLE,
  type ValidationFlagLike,
} from "./judge-data";
import {
  ExampleCard,
  ExpectationLine,
  RawJson,
  ScoreMeter,
  SeverityBadge,
  UsageBar,
  readJudgeError,
  useJudgeSubmit,
  type Usage,
} from "./judge-shared";

const DEMO_PROVIDER = "openai";

export interface ValidationResult {
  flags: ValidationFlagLike[];
  raw_judge_text: string;
  usage: Usage | null;
  pages_rendered: number;
}

export function ValidatePdfTab() {
  const [exampleLoaded, setExampleLoaded] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [extracted, setExtracted] = useState(
    JSON.stringify([{ field_name: "value" }], null, 2),
  );
  const [rubric, setRubric] = useState("");
  const [scoringMode, setScoringMode] = useState("likert_1_5");
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [judged, setJudged] = useState<{
    file: File;
    extracted: unknown;
  } | null>(null);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const { isLoading, result, setResult, run } =
    useJudgeSubmit<ValidationResult>();

  const judgedFile = judged?.file ?? null;
  useEffect(() => {
    if (!judgedFile) {
      setPdfUrl(null);
      return;
    }
    const url = URL.createObjectURL(judgedFile);
    setPdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [judgedFile]);

  async function loadExample() {
    setIsLoadingExample(true);
    try {
      const response = await fetch(INVOICE_EXAMPLE.pdfUrl);
      if (!response.ok)
        throw new Error(`Could not load ${INVOICE_EXAMPLE.pdfName}`);
      const blob = await response.blob();
      setFile(
        new File([blob], INVOICE_EXAMPLE.pdfName, { type: "application/pdf" }),
      );
      setExtracted(JSON.stringify(INVOICE_EXAMPLE.extracted, null, 2));
      setRubric(JSON.stringify(INVOICE_EXAMPLE.rubric, null, 2));
      setExampleLoaded(true);
      setResult(null);
      setJudged(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load example");
    } finally {
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit() {
    if (!file) {
      toast.error("Please select a PDF first");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(extracted);
    } catch (e) {
      toast.error(
        `Invalid extracted JSON: ${e instanceof Error ? e.message : "parse error"}`,
      );
      return;
    }
    if (rubric.trim()) {
      try {
        JSON.parse(rubric);
      } catch (e) {
        toast.error(
          `Invalid rubric JSON: ${e instanceof Error ? e.message : "parse error"}`,
        );
        return;
      }
    }
    await run(async (signal) => {
      const formData = new FormData();
      formData.append("pdf", file);
      formData.append("extracted", extracted);
      if (rubric.trim()) formData.append("rubric", rubric);
      formData.append("provider", DEMO_PROVIDER);
      formData.append("scoring_mode", scoringMode);
      const response = await apiFetch("/api/llm-judge/validate", {
        method: "POST",
        body: formData,
        signal,
      });
      if (!response.ok)
        throw new Error(await readJudgeError(response, "Validate call failed"));
      const data = (await response.json()) as ValidationResult;
      posthog.capture("llm_judge_run", {
        tab: "validate",
        provider: DEMO_PROVIDER,
        example: exampleLoaded,
      });
      setJudged({ file, extracted: parsed });
      return data;
    });
  }

  const grid = useMemo(
    () => (result && judged ? gridOf(judged.extracted, result.flags) : []),
    [result, judged],
  );
  const shown = onlyFlagged ? grid.filter((row) => row.flag) : grid;
  const suggested = result?.flags.filter((flag) => flag.suggested_value) ?? [];
  const corrected = useMemo(
    () =>
      result && judged
        ? JSON.stringify(
            applySuggestions(judged.extracted, result.flags),
            null,
            2,
          )
        : "",
    [result, judged],
  );
  const wrong = result?.flags.find(
    (flag) => flag.field === INVOICE_EXAMPLE.wrongField,
  );
  const isExample =
    exampleLoaded && judged?.file.name === INVOICE_EXAMPLE.pdfName;

  async function copyCorrected() {
    try {
      await navigator.clipboard.writeText(corrected);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  }

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Start from a case</h2>
        <div
          role="radiogroup"
          aria-label="Validation cases"
          className="grid gap-3 sm:grid-cols-2"
        >
          <ExampleCard
            title={INVOICE_EXAMPLE.title}
            summary={INVOICE_EXAMPLE.summary}
            tag="1 wrong field"
            selected={exampleLoaded}
            disabled={isLoading || isLoadingExample}
            onClick={() => void loadExample()}
          />
        </div>
      </section>

      <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>1. The PDF and the extraction</CardTitle>
            <CardDescription>
              The judge sees rendered PDF pages next to the extractor&apos;s
              output and flags fields that don&apos;t match. The first 5 pages
              are sent.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {isLoadingExample && (
              <p className="text-muted-foreground flex items-center gap-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading the example…
              </p>
            )}
            <label
              className={cn(
                "flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed p-4 transition-all",
                isLoading
                  ? "cursor-not-allowed opacity-50"
                  : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50",
              )}
            >
              <Upload className="text-muted-foreground h-6 w-6" />
              <p className="text-sm font-medium">
                {file ? file.name : "Drag & drop or click to choose a PDF"}
              </p>
              <p className="text-muted-foreground text-xs">
                PDF only · max 20 MB
              </p>
              <input
                type="file"
                accept=".pdf"
                disabled={isLoading}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setExampleLoaded(false);
                  setResult(null);
                  setJudged(null);
                }}
                className="sr-only"
              />
            </label>

            <div className="space-y-2">
              <Label htmlFor="validate-extracted">Extracted data (JSON)</Label>
              <Textarea
                id="validate-extracted"
                rows={7}
                value={extracted}
                onChange={(e) => {
                  setExtracted(e.target.value);
                  setExampleLoaded(false);
                }}
                disabled={isLoading}
                className="font-mono text-sm"
              />
              <p className="text-muted-foreground text-xs">
                A list of objects gives each item its own number; a single
                object holds document-level fields.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="rubric">Rubric (optional JSON)</Label>
              <Textarea
                id="rubric"
                rows={4}
                value={rubric}
                onChange={(e) => setRubric(e.target.value)}
                placeholder='{"field_checks": ["Quantity is integer units, not unit price"]}'
                disabled={isLoading}
                className="font-mono text-sm"
              />
              <p className="text-muted-foreground text-xs">
                Field-level rules for the judge, in plain sentences.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="scoring-mode">Scoring mode</Label>
              <Select
                value={scoringMode}
                onValueChange={setScoringMode}
                disabled={isLoading}
              >
                <SelectTrigger id="scoring-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="likert_1_5">Likert 1–5</SelectItem>
                  <SelectItem value="severity">Severity only</SelectItem>
                  <SelectItem value="additive">
                    Additive (per aspect)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={handleSubmit}
              disabled={isLoading || !file}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Validating…
                </>
              ) : (
                <>
                  <Gavel className="mr-2 h-4 w-4" />
                  Validate against the PDF
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4" aria-live="polite">
          {isLoading && (
            <LoadingCard
              message="Rendering the pages and calling the judge…"
              subMessage="Large PDFs take longer: only the first 5 pages are sent"
            />
          )}
          {result && !isLoading && judged && (
            <Card>
              <CardHeader>
                <CardTitle>
                  {result.flags.length === 0
                    ? "No issues flagged"
                    : `${result.flags.length} field${result.flags.length === 1 ? "" : "s"} flagged`}
                </CardTitle>
                <CardDescription>
                  {result.pages_rendered} page
                  {result.pages_rendered === 1 ? "" : "s"} shown to the judge ·{" "}
                  {grid.length - result.flags.length} of {grid.length} fields
                  not flagged
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {isExample && (
                  <ExpectationLine
                    met={Boolean(wrong)}
                    expectedText={`Expected: ${INVOICE_EXAMPLE.wrongField} flagged, with ${INVOICE_EXAMPLE.rightValue} suggested`}
                    detail={
                      wrong
                        ? wrong.suggested_value
                          ? `suggested ${wrong.suggested_value}`
                          : "no value suggested"
                        : "not flagged"
                    }
                  />
                )}

                <Tabs defaultValue="fields">
                  <TabsList>
                    <TabsTrigger value="fields">Fields</TabsTrigger>
                    <TabsTrigger value="pdf">The PDF</TabsTrigger>
                    <TabsTrigger value="corrected">
                      Corrected JSON
                      {suggested.length > 0 && (
                        <span className="text-muted-foreground ml-1.5 text-xs">
                          {suggested.length}
                        </span>
                      )}
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="fields" className="mt-3 space-y-2">
                    <label className="text-muted-foreground flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={onlyFlagged}
                        onChange={(e) => setOnlyFlagged(e.target.checked)}
                        className="accent-primary size-4"
                      />
                      Show only the flagged fields
                    </label>
                    <div className="overflow-x-auto rounded-md border">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr className="bg-muted/50 text-xs tracking-wider uppercase">
                            <th className="px-3 py-2 font-medium">Item</th>
                            <th className="px-3 py-2 font-medium">Field</th>
                            <th className="px-3 py-2 font-medium">Value</th>
                            <th className="px-3 py-2 font-medium">Judge</th>
                          </tr>
                        </thead>
                        <tbody>
                          {shown.map((row) => (
                            <tr
                              key={`${row.item}-${row.field}`}
                              className={cn(
                                "border-t align-top",
                                row.flag && "bg-rose-50/40",
                              )}
                            >
                              <td className="text-muted-foreground px-3 py-2 font-mono text-xs">
                                {row.item === -1 ? "doc" : row.item}
                              </td>
                              <td className="px-3 py-2 font-mono text-xs">
                                {row.field}
                              </td>
                              <td className="px-3 py-2 font-mono text-xs break-all">
                                {row.value}
                              </td>
                              <td className="space-y-1 px-3 py-2">
                                {row.flag ? (
                                  <>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <SeverityBadge
                                        severity={row.flag.severity}
                                      />
                                      <ScoreMeter score={row.flag.score} />
                                    </div>
                                    <p className="text-muted-foreground text-xs">
                                      {row.flag.reason}
                                    </p>
                                    {row.flag.suggested_value && (
                                      <p className="text-xs">
                                        <span className="text-muted-foreground">
                                          Suggested:
                                        </span>{" "}
                                        <span className="font-mono">
                                          {row.flag.suggested_value}
                                        </span>
                                      </p>
                                    )}
                                  </>
                                ) : (
                                  <Badge
                                    variant="outline"
                                    className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
                                  >
                                    matches
                                  </Badge>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </TabsContent>

                  <TabsContent value="pdf" className="mt-3">
                    {pdfUrl && (
                      <iframe
                        src={pdfUrl}
                        title="The PDF the judge saw"
                        className="h-[32rem] w-full rounded-md border"
                      />
                    )}
                  </TabsContent>

                  <TabsContent value="corrected" className="mt-3 space-y-2">
                    {suggested.length === 0 ? (
                      <p className="text-muted-foreground text-sm">
                        The judge suggested no corrections.
                      </p>
                    ) : (
                      <>
                        <p className="text-muted-foreground text-xs">
                          The extraction with each suggested value put in place
                          of the flagged one. Check it before you use it.
                        </p>
                        <pre className="bg-muted/40 max-h-72 overflow-auto rounded-md border p-3 font-mono text-xs">
                          {corrected}
                        </pre>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void copyCorrected()}
                        >
                          {copied ? <Check /> : <Copy />}
                          Copy the corrected JSON
                        </Button>
                      </>
                    )}
                  </TabsContent>
                </Tabs>
                <UsageBar usage={result.usage} />
                <RawJson data={result} />
              </CardContent>
            </Card>
          )}
          {!result && !isLoading && (
            <EmptyStateCard
              icon={FileText}
              title="No validation yet"
              description="Load the invoice case, or upload a PDF and paste an extracted JSON, then click Validate."
            />
          )}
        </div>
      </div>
    </div>
  );
}
