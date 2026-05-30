"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { PageTransition } from "@/components/demo/page-transition";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
} from "@/components/demo/result-card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileText,
  Gavel,
  Loader2,
  ScrollText,
  Scale,
  Sparkles,
  Upload,
  Users,
  XCircle,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

type Provider = "openai" | "azure" | "anthropic" | "google";

// Demo on Rahtissa konfiguroitu vain Azure-tunnuksilla; muiden providereiden
// valitseminen palauttaisi 503. Kovakoodataan Azure ja viestitään muiden
// vaativan extra-konfiguraatiota.
const DEMO_PROVIDER: Provider = "azure";

// Panel ajaa useampaa Azure-mallia rinnakkain — antaa kustannuksen ja
// nopeuden välisen disagreement-signaalin myös ilman cross-provider-tunnuksia.
// Kolmas tuomari (gpt-5.1) on tarkoituksella eri sukupolvea, jotta paneeli ei
// vain kopioi gpt-5.4-perheen vinoutumia.
const PANEL_JUDGES: { provider: Provider; model: string; label: string }[] = [
  { provider: "azure", model: "gpt-5.4-mini", label: "gpt-5.4-mini" },
  { provider: "azure", model: "gpt-5.4", label: "gpt-5.4" },
  { provider: "azure", model: "gpt-5.1", label: "gpt-5.1" },
];

const JUDGE_DOCS_URL =
  "https://gaik-project.github.io/gaik-toolkit/toolkit/evals/llm-judge/";
const JUDGE_BENCHMARK_DOCS_URL =
  "https://gaik-project.github.io/gaik-toolkit/toolkit/evals/llm-judge-benchmark/";

// Likert 1–5 ↔ severity mapping per gaik docs (1=wrong, 2-3=suspect, 4-5=ok).
const LIKERT_GUIDE: { score: string; severity: Severity; label: string }[] = [
  { score: "1", severity: "wrong", label: "Clearly wrong" },
  { score: "2–3", severity: "suspect", label: "Suspect — review before confirming" },
  { score: "4–5", severity: "ok", label: "Looks correct" },
];

interface Usage {
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  duration_s?: number | null;
  cost_usd?: number | null;
}

type Severity = "ok" | "suspect" | "wrong";

interface TextPairResult {
  equivalent: boolean;
  severity: Severity;
  score: number;
  reason: string;
  usage: Usage | null;
}

interface HallucinationFlag {
  field: string;
  value: string;
  severity: Severity;
  reason: string;
}

interface HallucinationResult {
  flags: HallucinationFlag[];
  raw_judge_text: string;
  usage: Usage | null;
}

interface ValidationFlag {
  item_index: number;
  field: string;
  severity: Severity;
  score: number;
  reason: string;
  suggested_value: string | null;
}

interface ValidationResult {
  flags: ValidationFlag[];
  raw_judge_text: string;
  usage: Usage | null;
  pages_rendered: number;
}

interface PanelEntry {
  provider: Provider;
  equivalent?: boolean;
  severity?: Severity;
  score?: number;
  reason?: string;
  usage?: Usage | null;
  error?: string;
}

interface SkippedEntry {
  provider: string;
  reason: string;
}

interface PanelResult {
  per_judge: PanelEntry[];
  skipped: SkippedEntry[];
  agreement_score: number;
  total_cost_usd: number;
  total_duration_s: number;
}

const SEVERITY_BADGE: Record<Severity, { className: string; icon: typeof CheckCircle2 }> = {
  ok: {
    className: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
    icon: CheckCircle2,
  },
  suspect: {
    className: "bg-amber-500/10 text-amber-600 border-amber-500/30",
    icon: AlertTriangle,
  },
  wrong: {
    className: "bg-rose-500/10 text-rose-600 border-rose-500/30",
    icon: XCircle,
  },
};

function SeverityBadge({ severity }: { severity: Severity }) {
  const { className, icon: Icon } = SEVERITY_BADGE[severity];
  return (
    <Badge variant="outline" className={`gap-1 ${className}`}>
      <Icon className="h-3 w-3" />
      {severity}
    </Badge>
  );
}

function UsageBar({ usage }: { usage: Usage | null | undefined }) {
  if (!usage) return null;
  const items: Array<{ label: string; value: string }> = [];
  if (usage.provider || usage.model) {
    items.push({
      label: "Model",
      value: `${usage.provider ?? ""}${usage.provider && usage.model ? " · " : ""}${
        usage.model ?? ""
      }`,
    });
  }
  if (usage.total_tokens != null) {
    items.push({ label: "Tokens", value: usage.total_tokens.toLocaleString() });
  }
  if (usage.duration_s != null) {
    items.push({ label: "Duration", value: `${usage.duration_s.toFixed(2)}s` });
  }
  if (usage.cost_usd != null) {
    items.push({ label: "Cost", value: `$${usage.cost_usd.toFixed(4)}` });
  }
  if (items.length === 0) return null;
  return (
    <div className="bg-muted/40 mb-4 grid grid-cols-2 gap-2 rounded-md border p-3 text-xs sm:grid-cols-4">
      {items.map((stat) => (
        <div key={stat.label}>
          <p className="text-muted-foreground">{stat.label}</p>
          <p className="font-mono">{stat.value}</p>
        </div>
      ))}
    </div>
  );
}

function RawJsonAccordion({ data, label = "Raw judge response" }: { data: unknown; label?: string }) {
  return (
    <Accordion type="single" collapsible className="w-full">
      <AccordionItem value="raw" className="border-none">
        <AccordionTrigger className="text-muted-foreground hover:text-foreground py-2 text-xs font-medium">
          {label}
        </AccordionTrigger>
        <AccordionContent>
          <pre className="bg-muted max-h-72 overflow-auto rounded p-3 text-xs">
            <code>{JSON.stringify(data, null, 2)}</code>
          </pre>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

// Compact Likert 1–5 ↔ severity guide. Surfaces the scoring rule the judge
// uses so non-technical users can read result badges. Source: gaik docs.
function ScoringGuide() {
  return (
    <div className="bg-muted/40 rounded-md border p-3 text-xs">
      <p className="text-muted-foreground mb-2 font-medium">
        How scoring works (Likert 1–5):
      </p>
      <div className="flex flex-wrap gap-2">
        {LIKERT_GUIDE.map((row) => (
          <div key={row.score} className="flex items-center gap-1.5">
            <Badge variant="secondary" className="font-mono">
              {row.score}
            </Badge>
            <SeverityBadge severity={row.severity} />
            <span className="text-muted-foreground">{row.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Shared submit plumbing for the tabs: owns the abort controller, isLoading,
// result state, and the standard AbortError / RateLimitError swallow. Each tab
// keeps its own validation and request body via the `run(signal)` callback.
function useJudgeSubmit<T>() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<T | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function run(executor: (signal: AbortSignal) => Promise<T>) {
    if (isLoading) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);
    try {
      setResult(await executor(abortRef.current.signal));
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return;
      toast.error(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return { isLoading, result, setResult, run };
}

// Extracts an error message from a !ok response, with a per-call fallback.
async function readJudgeError(response: Response, fallback: string): Promise<string> {
  const err = await response.json().catch(() => null);
  return err?.detail ?? fallback;
}

// ─────────────────── Text-pair tab ───────────────────

const TEXT_PAIR_PRESETS = [
  {
    label: "Paraphrase",
    expected: "The computer was not locked.",
    extracted: "Computer left unlocked at the workstation.",
  },
  {
    label: "Finnish morphology",
    expected: "kieppipeittaus",
    extracted: "kieppipeittauksessa",
  },
  {
    label: "Date format",
    expected: "26.8.2025",
    extracted: "2025-08-26",
  },
  {
    label: "Clearly different",
    expected: "Coolant leaked under unit B.",
    extracted: "Production output increased by 12 %.",
  },
];

function TextPairTab() {
  const [extracted, setExtracted] = useState("");
  const [expected, setExpected] = useState("");
  const [fieldName, setFieldName] = useState("");
  const { isLoading, result, setResult, run } = useJudgeSubmit<TextPairResult>();

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
      if (!response.ok) {
        throw new Error(await readJudgeError(response, "Judge call failed"));
      }
      const data = (await response.json()) as TextPairResult;
      posthog.capture("llm_judge_run", { tab: "text-pair", provider: DEMO_PROVIDER });
      return data;
    });
  }

  return (
    <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Two texts</CardTitle>
            <CardDescription>
              Compare an extractor&apos;s value with a reference. The judge handles
              paraphrasing, morphology, and date formats — no source document
              needed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-xs">Quick examples</Label>
              <div className="flex flex-wrap gap-2">
                {TEXT_PAIR_PRESETS.map((p) => (
                  <Button
                    key={p.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isLoading}
                    onClick={() => {
                      setExpected(p.expected);
                      setExtracted(p.extracted);
                      setResult(null);
                    }}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="expected">Expected (reference)</Label>
              <Textarea
                id="expected"
                rows={3}
                value={expected}
                onChange={(e) => setExpected(e.target.value)}
                placeholder="Ground-truth or reference text..."
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extracted">Extracted (candidate)</Label>
              <Textarea
                id="extracted"
                rows={3}
                value={extracted}
                onChange={(e) => setExtracted(e.target.value)}
                placeholder="Value produced by your extractor..."
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
            </div>

            <Button onClick={handleSubmit} disabled={isLoading} className="w-full" size="lg">
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
      </div>

      <div className="space-y-4">
        {isLoading && <LoadingCard message="Calling judge…" />}
        {result && !isLoading && (
          <ResultCard
            title="Verdict"
            description={result.equivalent ? "Texts are equivalent" : "Texts diverge"}
            copyContent={JSON.stringify(result, null, 2)}
          >
            <UsageBar usage={result.usage} />
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <SeverityBadge severity={result.severity} />
                <Badge variant="secondary" className="font-mono">
                  Likert {result.score}/5
                </Badge>
                <Badge variant={result.equivalent ? "default" : "outline"}>
                  equivalent: {String(result.equivalent)}
                </Badge>
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed">{result.reason}</p>
            </div>
          </ResultCard>
        )}
        {!result && !isLoading && (
          <EmptyStateCard
            icon={Scale}
            title="No judgement yet"
            description="Fill in the two texts and click Judge equivalence."
          />
        )}
      </div>
    </div>
  );
}

// ─────────────────── Hallucination tab ───────────────────

const HALLUCINATION_PRESET = {
  source:
    "Maintenance round on 2025-09-12. The technician reported a coolant leak under unit B and applied an absorbent mat. The leak source was not identified during this visit.",
  extracted: JSON.stringify(
    {
      report_date: "2025-09-12",
      location: "unit B",
      issue_type: "coolant leak",
      actions_taken: "absorbent mat applied",
      priority: "high",
      follow_up_date: "2025-09-15",
    },
    null,
    2,
  ),
};

function HallucinationsTab() {
  const [sourceText, setSourceText] = useState("");
  const [extracted, setExtracted] = useState("");
  const { isLoading, result, setResult, run } = useJudgeSubmit<HallucinationResult>();

  async function handleSubmit() {
    if (!sourceText.trim()) {
      toast.error("Source text is required");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(extracted);
    } catch (e) {
      toast.error(`Invalid JSON: ${e instanceof Error ? e.message : "parse error"}`);
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
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
      if (!response.ok) {
        throw new Error(await readJudgeError(response, "Judge call failed"));
      }
      const data = (await response.json()) as HallucinationResult;
      posthog.capture("llm_judge_run", { tab: "hallucinations", provider: DEMO_PROVIDER });
      return data;
    });
  }

  return (
    <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Grounded answer?</CardTitle>
            <CardDescription>
              Paste a source text and the extractor&apos;s output. The judge flags
              any field whose value is not supported by the source.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-xs">Quick example</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isLoading}
                onClick={() => {
                  setSourceText(HALLUCINATION_PRESET.source);
                  setExtracted(HALLUCINATION_PRESET.extracted);
                  setResult(null);
                }}
              >
                <Sparkles className="mr-2 h-3.5 w-3.5" />
                Load maintenance-report example
              </Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-text">Source text</Label>
              <Textarea
                id="source-text"
                rows={5}
                value={sourceText}
                onChange={(e) => setSourceText(e.target.value)}
                placeholder="The ground-truth document body (transcript, parsed text, etc.)"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label htmlFor="extracted-json">Extracted data (JSON)</Label>
                <span className="text-muted-foreground text-xs">
                  the fields the judge will check
                </span>
              </div>
              <Textarea
                id="extracted-json"
                rows={8}
                value={extracted}
                onChange={(e) => setExtracted(e.target.value)}
                placeholder='{"field_a": "value", ...}'
                disabled={isLoading}
                className="font-mono text-sm"
              />
              <p className="text-muted-foreground text-xs">
                Each <code>key: value</code> pair is treated as one field. Empty
                fields are skipped automatically.
              </p>
            </div>
            <Button onClick={handleSubmit} disabled={isLoading} className="w-full" size="lg">
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
      </div>

      <div className="space-y-4">
        {isLoading && <LoadingCard message="Reviewing fields…" />}
        {result && !isLoading && (
          <ResultCard
            title={
              result.flags.length === 0
                ? "All fields grounded"
                : `${result.flags.length} hallucinated field(s)`
            }
            description="Empty fields are ignored — the judge only flags problems."
            copyContent={JSON.stringify(result, null, 2)}
          >
            <UsageBar usage={result.usage} />
            {result.flags.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Every non-empty field is supported by the source text.
              </p>
            ) : (
              <div className="divide-y rounded-md border">
                {result.flags.map((flag) => (
                  <div key={flag.field} className="space-y-2 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-medium">{flag.field}</span>
                      <span className="text-muted-foreground font-mono text-xs">
                        = {JSON.stringify(flag.value)}
                      </span>
                      <SeverityBadge severity={flag.severity} />
                    </div>
                    <p className="text-muted-foreground text-sm">{flag.reason}</p>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4">
              <RawJsonAccordion data={result} />
            </div>
          </ResultCard>
        )}
        {!result && !isLoading && (
          <EmptyStateCard
            icon={ScrollText}
            title="No check yet"
            description="Paste a source text and an extracted JSON object, then click Detect."
          />
        )}
      </div>
    </div>
  );
}

// ─────────────────── PDF validation tab ───────────────────

const VALIDATE_PDF_EXAMPLE = {
  extracted: JSON.stringify(
    [
      {
        invoice_number: "INV-2025-014",
        vendor: "ACME Industrial Supplies",
        total_amount: 1284.5,
        currency: "EUR",
      },
    ],
    null,
    2,
  ),
  rubric: JSON.stringify(
    {
      field_checks: [
        "total_amount must equal the sum of line items, not the subtotal",
        "currency must be a 3-letter ISO code (e.g. EUR, USD)",
      ],
    },
    null,
    2,
  ),
};

function ValidatePdfTab() {
  const [file, setFile] = useState<File | null>(null);
  const [extracted, setExtracted] = useState(
    JSON.stringify([{ field_name: "value" }], null, 2),
  );
  const [rubric, setRubric] = useState("");
  const [scoringMode, setScoringMode] = useState("likert_1_5");
  const { isLoading, result, setResult, run } = useJudgeSubmit<ValidationResult>();

  async function handleSubmit() {
    if (!file) {
      toast.error("Please select a PDF first");
      return;
    }
    try {
      JSON.parse(extracted);
    } catch (e) {
      toast.error(`Invalid extracted JSON: ${e instanceof Error ? e.message : "parse error"}`);
      return;
    }
    if (rubric.trim()) {
      try {
        JSON.parse(rubric);
      } catch (e) {
        toast.error(`Invalid rubric JSON: ${e instanceof Error ? e.message : "parse error"}`);
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
      if (!response.ok) {
        throw new Error(await readJudgeError(response, "Validate call failed"));
      }
      const data = (await response.json()) as ValidationResult;
      posthog.capture("llm_judge_run", { tab: "validate", provider: DEMO_PROVIDER });
      return data;
    });
  }

  return (
    <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Upload PDF + extracted JSON</CardTitle>
            <CardDescription>
              The judge sees rendered PDF pages alongside the extractor&apos;s output
              and flags fields that don&apos;t match. First 5 pages are sent.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-xs">Quick example</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isLoading}
                onClick={() => {
                  setExtracted(VALIDATE_PDF_EXAMPLE.extracted);
                  setRubric(VALIDATE_PDF_EXAMPLE.rubric);
                  setResult(null);
                  toast("Example JSON loaded — now upload an invoice PDF");
                }}
              >
                <Sparkles className="mr-2 h-3.5 w-3.5" />
                Load invoice example
              </Button>
            </div>

            <label
              className={`flex min-h-30 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 transition-all ${
                isLoading
                  ? "cursor-not-allowed opacity-50"
                  : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
              }`}
            >
              <Upload className="text-muted-foreground h-7 w-7" />
              <p className="text-sm font-medium">
                {file ? file.name : "Drag & drop or click to choose a PDF"}
              </p>
              <p className="text-muted-foreground text-xs">PDF only · max 20 MB</p>
              <input
                type="file"
                accept=".pdf"
                disabled={isLoading}
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setFile(f);
                  setResult(null);
                }}
                className="sr-only"
              />
            </label>

            <div className="space-y-2">
              <Label htmlFor="validate-extracted">Extracted data (JSON)</Label>
              <Textarea
                id="validate-extracted"
                rows={6}
                value={extracted}
                onChange={(e) => setExtracted(e.target.value)}
                disabled={isLoading}
                className="font-mono text-sm"
              />
              <p className="text-muted-foreground text-xs">
                Use a list of objects for items (each gets its own <code>item_index</code>)
                or a single object for document-level fields.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="rubric">Rubric (optional JSON)</Label>
              <Textarea
                id="rubric"
                rows={3}
                value={rubric}
                onChange={(e) => setRubric(e.target.value)}
                placeholder='{"field_checks": ["Quantity is integer units, not unit price"]}'
                disabled={isLoading}
                className="font-mono text-sm"
              />
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
                  <SelectItem value="additive">Additive (per aspect)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button onClick={handleSubmit} disabled={isLoading || !file} className="w-full" size="lg">
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Validating…
                </>
              ) : (
                <>
                  <Gavel className="mr-2 h-4 w-4" />
                  Validate against PDF
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        {isLoading && (
          <LoadingCard
            message="Rendering pages + calling judge…"
            subMessage="Large PDFs take longer — only the first 5 pages are sent"
          />
        )}
        {result && !isLoading && (
          <ResultCard
            title={
              result.flags.length === 0
                ? "No issues flagged"
                : `${result.flags.length} flag(s)`
            }
            description={`${result.pages_rendered} page(s) shown to judge`}
            copyContent={JSON.stringify(result, null, 2)}
          >
            <UsageBar usage={result.usage} />
            {result.flags.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Every field matched the source document.
              </p>
            ) : (
              <div className="divide-y rounded-md border">
                {result.flags.map((flag, idx) => (
                  <div key={`${flag.item_index}-${flag.field}-${idx}`} className="space-y-2 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-mono text-xs">
                        item {flag.item_index === -1 ? "doc" : flag.item_index}
                      </Badge>
                      <span className="font-mono text-sm font-medium">{flag.field}</span>
                      <SeverityBadge severity={flag.severity} />
                      {flag.score > 0 && (
                        <Badge variant="secondary" className="font-mono">
                          {flag.score}/5
                        </Badge>
                      )}
                    </div>
                    <p className="text-muted-foreground text-sm">{flag.reason}</p>
                    {flag.suggested_value && (
                      <p className="text-xs">
                        <span className="text-muted-foreground">Suggested:</span>{" "}
                        <span className="font-mono">{flag.suggested_value}</span>
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4">
              <RawJsonAccordion data={result} />
            </div>
          </ResultCard>
        )}
        {!result && !isLoading && (
          <EmptyStateCard
            icon={FileText}
            title="No validation yet"
            description="Upload a PDF, paste an extracted JSON, and click Validate."
          />
        )}
      </div>
    </div>
  );
}

// ─────────────────── Panel tab ───────────────────

interface PanelPreset {
  label: string;
  expected: string;
  extracted: string;
  fieldName: string;
  hint: string;
}

const PANEL_PRESETS: PanelPreset[] = [
  {
    label: "Numeric mismatch",
    expected: "23",
    extracted: "23.3",
    fieldName: "quantity",
    hint: "Easy: every judge should flag this as wrong (score 1/5).",
  },
  {
    label: "Paraphrase",
    expected: "The computer was not locked.",
    extracted: "Computer left unlocked at the workstation.",
    fieldName: "incident_summary",
    hint: "Semantically equivalent — strict diff would fail, the judges shouldn't.",
  },
  {
    label: "Subtle near-match",
    expected:
      "Maintenance technician arrived at 14:35 and replaced the worn bearing on the conveyor. Belt tension re-adjusted; line restarted at 15:10. Root cause logged as bearing wear.",
    extracted:
      "Maintenance technician arrived at 14:30 and replaced the worn bearing on the conveyor. Belt tension was re-adjusted and the line restarted at 15:10. Cause: bearing wear.",
    fieldName: "maintenance_log_entry",
    hint:
      "Two factual differences (14:35 → 14:30 and small paraphrasing). Judges may split — that's the disagreement signal a panel is meant to surface.",
  },
];

// Summarises the panel: surfaces the majority-vote severity, median score,
// and a friendly read of the agreement rate per the gaik docs guidance.
function PanelAggregation({ result }: { result: PanelResult }) {
  const successful = result.per_judge.filter(
    (e): e is PanelEntry & { severity: Severity } => !!e.severity,
  );
  if (successful.length === 0) return null;

  const severityCounts = successful.reduce<Record<Severity, number>>(
    (acc, e) => {
      acc[e.severity] = (acc[e.severity] ?? 0) + 1;
      return acc;
    },
    { ok: 0, suspect: 0, wrong: 0 },
  );
  // Tie-breaker per docs: when judges split evenly, surface the harshest verdict.
  const severityRank: Record<Severity, number> = { ok: 0, suspect: 1, wrong: 2 };
  const maxCount = Math.max(...Object.values(severityCounts));
  const majority = (Object.keys(severityCounts) as Severity[])
    .filter((s) => severityCounts[s] === maxCount)
    .sort((a, b) => severityRank[b] - severityRank[a])[0];

  const scores = successful
    .map((e) => e.score)
    .filter((s): s is number => typeof s === "number" && s > 0)
    .sort((a, b) => a - b);
  const median = scores.length
    ? scores[Math.floor((scores.length - 1) / 2)]
    : null;

  const ratio = result.agreement_score;
  const agreementText =
    ratio >= 0.99
      ? "Unanimous — every judge agreed."
      : ratio >= 0.66
        ? "Strong agreement — majority lines up."
        : "Mixed — treat the panel verdict as advisory.";

  return (
    <div className="bg-muted/40 mb-4 space-y-2 rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-xs">Panel verdict:</span>
        <SeverityBadge severity={majority} />
        {median != null && (
          <Badge variant="secondary" className="font-mono">
            median {median}/5
          </Badge>
        )}
        <span className="text-muted-foreground text-xs">
          {severityCounts.wrong > 0 && `${severityCounts.wrong} wrong · `}
          {severityCounts.suspect > 0 && `${severityCounts.suspect} suspect · `}
          {severityCounts.ok > 0 && `${severityCounts.ok} ok`}
        </span>
      </div>
      <p className="text-muted-foreground text-xs leading-relaxed">
        {agreementText}{" "}
        {ratio < 0.99 && (
          <span>
            Tie-breaker rule: when judges split, the panel surfaces the
            harshest verdict so issues aren&apos;t silently dropped.
          </span>
        )}
      </p>
    </div>
  );
}

function PanelTab() {
  const [extracted, setExtracted] = useState("");
  const [expected, setExpected] = useState("");
  const [fieldName, setFieldName] = useState("");
  const [activeHint, setActiveHint] = useState<string | null>(null);
  const { isLoading, result, setResult, run } = useJudgeSubmit<PanelResult>();

  async function handleSubmit() {
    if (!extracted.trim() || !expected.trim()) {
      toast.error("Please fill in both texts");
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
          judges: PANEL_JUDGES.map((j) => ({
            provider: j.provider,
            model: j.model,
          })),
        }),
        signal,
      });
      if (!response.ok) {
        // Panel-vastauksen detail voi olla joko string tai { message, ... } -objekti.
        const err = await response.json().catch(() => null);
        const detail =
          typeof err?.detail === "string"
            ? err.detail
            : err?.detail?.message ?? "Panel call failed";
        throw new Error(detail);
      }
      const data = (await response.json()) as PanelResult;
      posthog.capture("llm_judge_run", { tab: "panel", provider: "panel" });
      return data;
    });
  }

  return (
    <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1.5">
                <CardTitle>Run multiple judges in parallel</CardTitle>
                <CardDescription>
                  Sends the same text-pair to {PANEL_JUDGES.length} Azure models
                  and reports how often they agree. A multi-model panel debiases
                  any single model&apos;s quirks without requiring extra provider
                  credentials.
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
              <span className="text-muted-foreground">Judges:</span>
              {PANEL_JUDGES.map((j) => (
                <Badge key={j.label} variant="secondary" className="font-mono">
                  azure · {j.label}
                </Badge>
              ))}
            </div>

            <div className="space-y-2">
              <Label className="text-xs">Quick examples</Label>
              <div className="flex flex-wrap gap-2">
                {PANEL_PRESETS.map((p) => (
                  <Button
                    key={p.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isLoading}
                    onClick={() => {
                      setExpected(p.expected);
                      setExtracted(p.extracted);
                      setFieldName(p.fieldName);
                      setActiveHint(p.hint);
                      setResult(null);
                    }}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
              {activeHint && (
                <p className="text-muted-foreground text-xs leading-relaxed">
                  {activeHint}
                </p>
              )}
            </div>

            <ScoringGuide />

            <div className="space-y-2">
              <Label htmlFor="panel-expected">Expected</Label>
              <Textarea
                id="panel-expected"
                rows={3}
                value={expected}
                onChange={(e) => setExpected(e.target.value)}
                placeholder="Reference text..."
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="panel-extracted">Extracted</Label>
              <Textarea
                id="panel-extracted"
                rows={3}
                value={extracted}
                onChange={(e) => setExtracted(e.target.value)}
                placeholder="Candidate text..."
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
            <Button onClick={handleSubmit} disabled={isLoading} className="w-full" size="lg">
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Running panel…
                </>
              ) : (
                <>
                  <Users className="mr-2 h-4 w-4" />
                  Run judge panel
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        {isLoading && (
          <LoadingCard
            message={`${PANEL_JUDGES.length} judges, sequential calls…`}
            subMessage={`Wall-clock = sum of ${PANEL_JUDGES.length} judges`}
          />
        )}
        {result && !isLoading && (
          <ResultCard
            title={`Panel: ${(result.agreement_score * 100).toFixed(0)}% agreement`}
            description={`Total $${result.total_cost_usd.toFixed(4)} · ${result.total_duration_s.toFixed(2)}s`}
            copyContent={JSON.stringify(result, null, 2)}
          >
            <PanelAggregation result={result} />
            <div className="space-y-3">
              {result.per_judge.map((entry) => (
                <div key={entry.provider} className="rounded-md border p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="font-mono">
                      {entry.provider}
                    </Badge>
                    {entry.severity && <SeverityBadge severity={entry.severity} />}
                    {entry.score != null && (
                      <Badge variant="secondary" className="font-mono">
                        {entry.score}/5
                      </Badge>
                    )}
                    {entry.equivalent != null && (
                      <Badge variant={entry.equivalent ? "default" : "outline"}>
                        equivalent: {String(entry.equivalent)}
                      </Badge>
                    )}
                  </div>
                  {entry.usage && <UsageBar usage={entry.usage} />}
                  {entry.reason && (
                    <p className="text-muted-foreground text-sm">{entry.reason}</p>
                  )}
                  {entry.error && (
                    <p className="text-destructive text-sm">{entry.error}</p>
                  )}
                </div>
              ))}
              {result.skipped.length > 0 && (
                <div className="bg-amber-500/10 rounded-md border border-amber-500/30 p-3">
                  <p className="mb-1 text-xs font-medium text-amber-700 dark:text-amber-400">
                    Skipped judges
                  </p>
                  {result.skipped.map((s) => (
                    <p key={s.provider} className="text-muted-foreground text-xs">
                      <span className="font-mono">{s.provider}</span>: {s.reason}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </ResultCard>
        )}
        {!result && !isLoading && (
          <EmptyStateCard
            icon={Users}
            title="No panel run yet"
            description={`Fill in both texts and run all ${PANEL_JUDGES.length} judges.`}
          />
        )}
      </div>
    </div>
  );
}

// ─────────────────── Page shell ───────────────────

export default function LlmJudgePage() {
  return (
    <PageTransition>
      <DemoPageHeader
        icon={Scale}
        title="LLM-as-Judge"
        description="Score extractor output, detect hallucinations, compare texts, and run a multi-model judge panel."
        className="mb-8"
      />

      <Tabs defaultValue="text-pair" className="space-y-6">
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="text-pair">Text pair</TabsTrigger>
          <TabsTrigger value="hallucinations">Hallucinations</TabsTrigger>
          <TabsTrigger value="validate">Validate PDF</TabsTrigger>
          <TabsTrigger value="panel">Panel</TabsTrigger>
        </TabsList>

        <TabsContent value="text-pair">
          <TextPairTab />
        </TabsContent>
        <TabsContent value="hallucinations">
          <HallucinationsTab />
        </TabsContent>
        <TabsContent value="validate">
          <ValidatePdfTab />
        </TabsContent>
        <TabsContent value="panel">
          <PanelTab />
        </TabsContent>
      </Tabs>

      <div className="mt-8">
        <HowItWorksCard description="An LLM-as-judge built on the GAIK toolkit's validators package.">
          <p>
            <strong>1. Text pair.</strong> Two strings in, one verdict out. Useful when
            an extractor returns free-text values that paraphrase the ground truth — exact
            matching scores those wrong; the judge sees them as equivalent.
          </p>
          <p>
            <strong>2. Hallucinations.</strong> Given a source text and a JSON object,
            the judge flags fields whose values are not implied by the source. Empty
            fields are skipped automatically.
          </p>
          <p>
            <strong>3. Validate PDF.</strong> Renders the PDF&apos;s first pages, sends
            them to a vision-capable model alongside the extracted JSON, and returns
            per-field severity, Likert score, and a suggested correction. Use the rubric
            field to pass field-level instructions.
          </p>
          <p>
            <strong>4. Panel.</strong> Runs the text-pair check across three
            Azure models (gpt-5.4-mini, gpt-5.4 and gpt-5.1) and reports an
            agreement score. Verdicts aggregate by majority vote; ties resolve
            to the harshest severity so problems don&apos;t get silently dropped.
            Cross-provider panels (Azure + Claude + Gemini) are supported by the
            library but require extra credentials — see{" "}
            <a
              href={JUDGE_DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:no-underline"
            >
              the LLM-as-Judge docs
            </a>{" "}
            for setup, and the{" "}
            <a
              href={JUDGE_BENCHMARK_DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:no-underline"
            >
              JudgeBench prompt benchmark
            </a>{" "}
            for the research behind the scoring prompts.
          </p>
        </HowItWorksCard>
      </div>
    </PageTransition>
  );
}
