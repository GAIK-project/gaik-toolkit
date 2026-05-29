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

const PROVIDER_OPTIONS: { value: Provider; label: string }[] = [
  { value: "azure", label: "Azure OpenAI (default)" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Claude (Anthropic)" },
  { value: "google", label: "Gemini (Google)" },
];

const PANEL_PROVIDERS: Provider[] = ["azure", "anthropic", "google"];

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
  const [provider, setProvider] = useState<Provider>("azure");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TextPairResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleSubmit() {
    if (isLoading) return;
    if (!extracted.trim() || !expected.trim()) {
      toast.error("Please fill in both texts");
      return;
    }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch("/api/llm-judge/text-pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extracted_text: extracted,
          expected_text: expected,
          field_name: fieldName || undefined,
          provider,
        }),
        signal: abortRef.current.signal,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail ?? "Judge call failed");
      }
      const data = (await response.json()) as TextPairResult;
      setResult(data);
      posthog.capture("llm_judge_run", { tab: "text-pair", provider });
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return;
      toast.error(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
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

            <div className="grid gap-4 sm:grid-cols-2">
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
              <div className="space-y-2">
                <Label htmlFor="provider-tp">Provider</Label>
                <Select
                  value={provider}
                  onValueChange={(v) => setProvider(v as Provider)}
                  disabled={isLoading}
                >
                  <SelectTrigger id="provider-tp">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PROVIDER_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
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
  const [provider, setProvider] = useState<Provider>("azure");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<HallucinationResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleSubmit() {
    if (isLoading) return;
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
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch("/api/llm-judge/hallucinations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_text: sourceText,
          extracted: parsed,
          provider,
        }),
        signal: abortRef.current.signal,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail ?? "Judge call failed");
      }
      const data = (await response.json()) as HallucinationResult;
      setResult(data);
      posthog.capture("llm_judge_run", { tab: "hallucinations", provider });
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return;
      toast.error(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1.5">
                <CardTitle>Grounded JSON?</CardTitle>
                <CardDescription>
                  Paste a source text and an extracted JSON object. The judge flags
                  any field whose value is not supported by the source.
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={isLoading}
                onClick={() => {
                  setSourceText(HALLUCINATION_PRESET.source);
                  setExtracted(HALLUCINATION_PRESET.extracted);
                  setResult(null);
                }}
              >
                Try example
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
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
              <Label htmlFor="extracted-json">Extracted JSON</Label>
              <Textarea
                id="extracted-json"
                rows={8}
                value={extracted}
                onChange={(e) => setExtracted(e.target.value)}
                placeholder='{"field_a": "value", ...}'
                disabled={isLoading}
                className="font-mono text-sm"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="provider-hl">Provider</Label>
              <Select
                value={provider}
                onValueChange={(v) => setProvider(v as Provider)}
                disabled={isLoading}
              >
                <SelectTrigger id="provider-hl">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

function ValidatePdfTab() {
  const [file, setFile] = useState<File | null>(null);
  const [extracted, setExtracted] = useState(
    JSON.stringify([{ field_name: "value" }], null, 2),
  );
  const [rubric, setRubric] = useState("");
  const [provider, setProvider] = useState<Provider>("azure");
  const [scoringMode, setScoringMode] = useState("likert_1_5");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleSubmit() {
    if (isLoading) return;
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
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("pdf", file);
      formData.append("extracted", extracted);
      if (rubric.trim()) formData.append("rubric", rubric);
      formData.append("provider", provider);
      formData.append("scoring_mode", scoringMode);
      const response = await apiFetch("/api/llm-judge/validate", {
        method: "POST",
        body: formData,
        signal: abortRef.current.signal,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail ?? "Validate call failed");
      }
      const data = (await response.json()) as ValidationResult;
      setResult(data);
      posthog.capture("llm_judge_run", { tab: "validate", provider });
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return;
      toast.error(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
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
            <label
              className={`flex min-h-[120px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 transition-all ${
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
              <Label htmlFor="validate-extracted">Extracted JSON</Label>
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

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="provider-vp">Provider</Label>
                <Select
                  value={provider}
                  onValueChange={(v) => setProvider(v as Provider)}
                  disabled={isLoading}
                >
                  <SelectTrigger id="provider-vp">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PROVIDER_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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

function PanelTab() {
  const [extracted, setExtracted] = useState("");
  const [expected, setExpected] = useState("");
  const [fieldName, setFieldName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<PanelResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleSubmit() {
    if (isLoading) return;
    if (!extracted.trim() || !expected.trim()) {
      toast.error("Please fill in both texts");
      return;
    }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch("/api/llm-judge/panel/text-pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extracted_text: extracted,
          expected_text: expected,
          field_name: fieldName || undefined,
          providers: PANEL_PROVIDERS,
        }),
        signal: abortRef.current.signal,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => null);
        const detail =
          typeof err?.detail === "string"
            ? err.detail
            : err?.detail?.message ?? "Panel call failed";
        throw new Error(detail);
      }
      const data = (await response.json()) as PanelResult;
      setResult(data);
      posthog.capture("llm_judge_run", { tab: "panel", provider: "panel" });
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return;
      toast.error(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Run three judges in parallel</CardTitle>
            <CardDescription>
              Sends the same text-pair to Azure OpenAI, Anthropic Claude, and Google
              Gemini and reports how often they agree. Provider extras must be installed
              for each judge; missing ones are skipped.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
            message="Three providers, sequential calls…"
            subMessage="Wall-clock = sum of three judges"
          />
        )}
        {result && !isLoading && (
          <ResultCard
            title={`Panel: ${(result.agreement_score * 100).toFixed(0)}% agreement`}
            description={`Total $${result.total_cost_usd.toFixed(4)} · ${result.total_duration_s.toFixed(2)}s`}
            copyContent={JSON.stringify(result, null, 2)}
          >
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
                    Skipped providers
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
            description="Fill in both texts and run all three judges."
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
        description="Score extractor output, detect hallucinations, compare texts, and run a multi-provider panel."
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
        <HowItWorksCard description="A multi-provider LLM-as-judge built on the GAIK toolkit's validators package.">
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
            <strong>4. Panel.</strong> Runs the text-pair check across Azure OpenAI,
            Claude, and Gemini, then reports an agreement score. Providers missing
            credentials are skipped — at least two judges are required.
          </p>
        </HowItWorksCard>
      </div>
    </PageTransition>
  );
}
