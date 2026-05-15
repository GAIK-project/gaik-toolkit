"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { PageTransition } from "@/components/demo/page-transition";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { formatFieldName, formatFileSize } from "@/lib/utils";
import {
  CheckCircle,
  File as FileIcon,
  FileCode2,
  FileStack,
  Loader2,
  ScanEye,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

const ACCEPTED_EXTENSIONS = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".tiff",
  ".bmp",
];
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");
const MAX_FILE_MB = 20;

const EXAMPLE_FILES = [
  "/vision-extractor-example/PO.pdf",
  "/vision-extractor-example/BOM1.pdf",
  "/vision-extractor-example/BOM2.pdf",
  "/vision-extractor-example/BOM3.pdf",
];

const EXAMPLE_REQUIREMENTS = `Extract key fields from a Purchase Order (PO) and align each PO item with the matching Bill of Materials (BOM) via Material Number.

For every PO item, extract: Material Number, Quantity, Description, Delivery Date (DD/MM/YYYY). Then look up the matching BOM (where ID = Material Number) and add: Type Part Designation, Dimensions.

Also extract from the PO header: Order Date, Buyer, Sales Person, Shipping Address, Payment Terms.`;

const REQUIREMENT_PRESETS: { label: string; description: string; text: string }[] = [
  {
    label: "Invoice / receipt",
    description: "Sender, totals, line items",
    text: "Extract invoice number, issue date, due date, sender name and address, recipient name and address, subtotal, tax, total amount, currency, and a list of line items (description, quantity, unit price, line total).",
  },
  {
    label: "Document metadata",
    description: "Title, author, dates — works for reports & papers",
    text: "Extract document title, authors (list), organization or publisher, publication date, document type (e.g. report, paper, brief), executive summary or abstract (1–2 sentences), key topics covered (list of short phrases), and any URLs or references mentioned.",
  },
  {
    label: "Contract",
    description: "Parties, dates, key clauses",
    text: "Extract the parties involved (list with name and role), contract type, effective date, expiration or termination date, payment terms, key obligations (list), governing law / jurisdiction, and any notable exceptions or termination clauses.",
  },
  {
    label: "Form / application",
    description: "Generic structured form fields",
    text: "Extract every labelled field you see in this form together with its value. Group related fields and preserve checkbox / radio selections as their selected option text.",
  },
];

interface GeneratedSchema {
  schema_code: string;
  schema_name: string;
  structure_type: string;
  schema_id: string;
  fields: Array<{
    name: string;
    type: string;
    description: string;
    required: boolean;
  }>;
}

type Provider = "openai" | "claude" | "google";

interface VerificationEntry {
  value: unknown;
  confidence_score?: number;
  confidence_reason?: string;
}

interface VisionExtractResult {
  data: Record<string, unknown>;
  verification: Record<string, VerificationEntry | VerificationEntry[]> | null;
  model: string;
  documents_processed: number;
  duration_s: number;
  usage: {
    provider?: string | null;
    model?: string | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    thinking_tokens?: number | null;
    total_tokens?: number | null;
    cost_usd?: number | null;
  } | null;
}

function validateFile(file: File): string | null {
  const ext = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  if (!ACCEPTED_EXTENSIONS.includes(ext)) {
    return `Unsupported type: ${ext}. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`;
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return `File too large (max ${MAX_FILE_MB}MB)`;
  }
  return null;
}

function formatNumeric(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

interface FileListRowProps {
  file: File;
  disabled: boolean;
  onRemove: () => void;
}

function FileListRow({ file, disabled, onRemove }: FileListRowProps) {
  return (
    <div className="border-success/30 bg-success/10 flex items-center gap-2 rounded-md border p-2">
      <CheckCircle className="text-success h-4 w-4 shrink-0" />
      <FileIcon className="text-muted-foreground h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{file.name}</p>
        <p className="text-muted-foreground text-xs">{formatFileSize(file.size)}</p>
      </div>
      <button
        onClick={onRemove}
        disabled={disabled}
        className="hover:bg-success/20 rounded-full p-1 transition-colors"
        aria-label={`Remove ${file.name}`}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

interface UsageStatsProps {
  usage: NonNullable<VisionExtractResult["usage"]>;
}

function UsageStats({ usage }: UsageStatsProps) {
  const stats: Array<{ label: string; value: string; mono?: boolean; bold?: boolean }> = [];
  if (usage.total_tokens != null) {
    stats.push({
      label: "Tokens",
      value: usage.total_tokens.toLocaleString(),
      bold: true,
    });
  }
  if (usage.input_tokens != null) {
    stats.push({ label: "Input", value: usage.input_tokens.toLocaleString() });
  }
  if (usage.output_tokens != null) {
    stats.push({ label: "Output", value: usage.output_tokens.toLocaleString() });
  }
  if (usage.cost_usd != null) {
    stats.push({ label: "Cost", value: `$${usage.cost_usd.toFixed(4)}`, bold: true });
  }

  if (stats.length === 0) return null;

  return (
    <div className="bg-muted/40 mb-4 grid grid-cols-2 gap-2 rounded-md border p-3 text-xs sm:grid-cols-4">
      {stats.map((stat) => (
        <div key={stat.label}>
          <p className="text-muted-foreground">{stat.label}</p>
          <p className={`font-mono ${stat.bold ? "font-medium" : ""}`}>{stat.value}</p>
        </div>
      ))}
    </div>
  );
}

interface ExtractedFieldRowProps {
  fieldKey: string;
  value: unknown;
  verification?: VerificationEntry | VerificationEntry[];
}

function ExtractedFieldRow({ fieldKey, value, verification }: ExtractedFieldRowProps) {
  const isList = Array.isArray(value);
  const scalarVerification =
    verification && !Array.isArray(verification) ? verification : null;

  return (
    <div className="space-y-2 p-3">
      <div className="flex items-start gap-4">
        <span className="min-w-32 text-sm font-medium">{formatFieldName(fieldKey)}</span>
        <span className="text-muted-foreground flex-1 text-sm whitespace-pre-wrap">
          {isList
            ? `${(value as unknown[]).length} item(s)`
            : formatNumeric(value)}
        </span>
      </div>
      {scalarVerification && (
        <div className="ml-32 flex items-center gap-2 text-xs">
          <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 font-mono">
            {Math.round((scalarVerification.confidence_score ?? 0) * 100)}%
          </span>
          <span className="text-muted-foreground">
            {scalarVerification.confidence_reason ?? ""}
          </span>
        </div>
      )}
      {isList && (
        <pre className="bg-muted/30 ml-32 max-h-64 overflow-auto rounded p-2 text-xs">
          <code>{JSON.stringify(value, null, 2)}</code>
        </pre>
      )}
    </div>
  );
}

interface SchemaPreviewProps {
  schema: GeneratedSchema;
}

function SchemaPreview({ schema }: SchemaPreviewProps) {
  return (
    <Accordion type="single" collapsible defaultValue="schema" className="w-full">
      <AccordionItem value="schema" className="border-none">
        <AccordionTrigger className="text-sm">
          Generated schema · {schema.schema_name} ·{" "}
          {pluralize(schema.fields.length, "field")}
        </AccordionTrigger>
        <AccordionContent>
          <div className="bg-muted/50 space-y-3 rounded-md border p-3">
            <pre className="bg-background max-h-72 overflow-auto rounded p-3 text-xs">
              <code>{schema.schema_code}</code>
            </pre>
            <div>
              <p className="mb-1 text-xs font-medium">Fields</p>
              <div className="space-y-0.5">
                {schema.fields.map((field) => (
                  <div key={field.name} className="text-muted-foreground text-xs">
                    <span className="font-mono">{field.name}</span>
                    <span className="mx-1">:</span>
                    <span>{field.type}</span>
                    {field.required && (
                      <span className="ml-1 text-orange-500">*</span>
                    )}
                    {field.description && (
                      <span className="text-muted-foreground/80 ml-2">
                        — {field.description}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

export default function VisionExtractorPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [userRequirements, setUserRequirements] = useState("");
  const [provider, setProvider] = useState<Provider>("openai");
  const [includeVerification, setIncludeVerification] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);
  const [generatedSchema, setGeneratedSchema] = useState<GeneratedSchema | null>(
    null,
  );
  const [result, setResult] = useState<VisionExtractResult | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Clear preview when requirements change so the user knows it's stale
  function handleRequirementsChange(value: string): void {
    setUserRequirements(value);
    setGeneratedSchema(null);
  }

  async function handlePreviewSchema(): Promise<void> {
    if (isGeneratingSchema || isLoading) return;
    if (!userRequirements.trim()) {
      toast.error("Please describe what to extract first");
      return;
    }
    setIsGeneratingSchema(true);
    try {
      const response = await apiFetch("/api/extract-vision/generate-schema", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_requirements: userRequirements }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate schema");
      }
      const data = (await response.json()) as GeneratedSchema;
      setGeneratedSchema(data);
      toast.success("Schema generated — review before extracting");
    } catch (err) {
      if (err instanceof RateLimitError) return;
      toast.error(err instanceof Error ? err.message : "Failed to generate schema");
    } finally {
      setIsGeneratingSchema(false);
    }
  }

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  function addFiles(incoming: FileList | File[]): void {
    const accepted: File[] = [];
    const errors: string[] = [];
    for (const file of Array.from(incoming)) {
      const error = validateFile(file);
      if (error) {
        errors.push(`${file.name}: ${error}`);
        continue;
      }
      if (files.some((f) => f.name === file.name && f.size === file.size)) {
        continue;
      }
      accepted.push(file);
    }
    if (errors.length > 0) {
      toast.error(errors.join("\n"));
    }
    if (accepted.length > 0) {
      setFiles([...files, ...accepted]);
    }
  }

  function removeFile(index: number): void {
    setFiles(files.filter((_, i) => i !== index));
  }

  async function handleLoadExample(): Promise<void> {
    if (isLoadingExample || isLoading) return;
    setIsLoadingExample(true);
    try {
      const fetched = await Promise.all(
        EXAMPLE_FILES.map(async (url) => {
          const res = await fetch(url);
          if (!res.ok) throw new Error(`Failed to load ${url}`);
          const blob = await res.blob();
          const name = url.split("/").pop() ?? "example.pdf";
          return new File([blob], name, { type: blob.type || "application/pdf" });
        }),
      );
      setFiles(fetched);
      setUserRequirements(EXAMPLE_REQUIREMENTS);
      setResult(null);
      toast.success("Example loaded — PO + 3 BOMs ready to extract");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load example");
    } finally {
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading) return;
    if (files.length === 0) {
      toast.error("Please select at least one PDF or image");
      return;
    }
    if (!userRequirements.trim()) {
      toast.error("Please describe what to extract");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      formData.append("user_requirements", userRequirements);
      formData.append("model_provider", provider);
      formData.append("include_verification", includeVerification ? "true" : "false");

      const response = await apiFetch("/api/extract-vision", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Vision extraction failed");
      }

      const data = (await response.json()) as VisionExtractResult;
      setResult(data);

      posthog.capture("vision_extracted", {
        provider,
        documents_processed: data.documents_processed,
        include_verification: includeVerification,
        total_tokens: data.usage?.total_tokens ?? 0,
      });

      toast.success("Vision extraction complete");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  const verificationMap =
    includeVerification && result?.verification ? result.verification : null;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={ScanEye}
        title="Vision Extractor"
        description="Extract structured data from PDFs and images in a single LLM call — multi-document, no intermediate parse step."
        className="mb-8"
      />

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1.5">
                  <CardTitle>Documents</CardTitle>
                  <CardDescription>
                    Upload one or more PDF or image files. The model sees them
                    all together — useful for cross-document tasks like
                    matching a purchase order with its bills of materials.
                  </CardDescription>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLoadExample}
                  disabled={isLoading || isLoadingExample}
                  className="shrink-0"
                >
                  {isLoadingExample ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileStack className="mr-2 h-4 w-4" />
                  )}
                  Try example
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <label
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!isLoading && e.dataTransfer.files.length > 0) {
                    addFiles(e.dataTransfer.files);
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (!isLoading) setIsDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                }}
                className={`flex min-h-[140px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 transition-all ${
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
                } ${isLoading ? "cursor-not-allowed opacity-50" : ""}`}
              >
                <Upload
                  className={`h-8 w-8 ${isDragging ? "text-primary" : "text-muted-foreground"}`}
                />
                <div className="text-center">
                  <p className="text-sm font-medium">
                    {isDragging
                      ? "Drop files here"
                      : "Drag & drop or click to add files"}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    PDF, PNG, JPG, GIF, WEBP, TIFF, BMP — up to {MAX_FILE_MB}MB each
                  </p>
                </div>
                <input
                  type="file"
                  accept={ACCEPT_ATTR}
                  multiple
                  disabled={isLoading}
                  onChange={(e) => {
                    if (e.target.files) {
                      addFiles(e.target.files);
                      e.target.value = "";
                    }
                  }}
                  className="sr-only"
                />
              </label>

              {files.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-xs">
                    {pluralize(files.length, "file")} selected
                  </Label>
                  <div className="max-h-48 space-y-1.5 overflow-auto">
                    {files.map((file, index) => (
                      <FileListRow
                        key={`${file.name}-${index}`}
                        file={file}
                        disabled={isLoading}
                        onRemove={() => removeFile(index)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Extraction</CardTitle>
              <CardDescription>
                Describe in plain language what fields you want — the toolkit
                turns your description into a typed Pydantic schema and the
                model fills it in. Preview the schema below before extracting
                if you want to see exactly what will be returned.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-xs">Quick-start prompts</Label>
                <div className="flex flex-wrap gap-2">
                  {REQUIREMENT_PRESETS.map((preset) => (
                    <Button
                      key={preset.label}
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleRequirementsChange(preset.text)}
                      disabled={isLoading || isGeneratingSchema}
                      title={preset.description}
                      className="h-auto whitespace-normal text-left"
                    >
                      <span className="font-medium">{preset.label}</span>
                      <span className="text-muted-foreground ml-2 hidden text-xs sm:inline">
                        {preset.description}
                      </span>
                    </Button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="requirements">Requirements</Label>
                <Textarea
                  id="requirements"
                  value={userRequirements}
                  onChange={(e) => handleRequirementsChange(e.target.value)}
                  placeholder="e.g. Extract company name, total amount, date, and a list of line items (description, quantity, unit price) from this invoice."
                  disabled={isLoading || isGeneratingSchema}
                  rows={6}
                />
                <p className="text-muted-foreground text-xs">
                  Be specific about field names and types. The clearer your
                  description, the better the generated schema.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="provider">Model Provider</Label>
                  <Select
                    value={provider}
                    onValueChange={(v) => setProvider(v as Provider)}
                    disabled={isLoading}
                  >
                    <SelectTrigger id="provider">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openai">OpenAI / Azure</SelectItem>
                      <SelectItem value="claude">
                        Claude (Anthropic Foundry)
                      </SelectItem>
                      <SelectItem value="google">
                        Google (Vertex AI)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="verification">Per-field verification</Label>
                  <div className="flex h-9 items-center gap-3 rounded-md border px-3">
                    <Switch
                      id="verification"
                      checked={includeVerification}
                      onCheckedChange={setIncludeVerification}
                      disabled={isLoading}
                    />
                    <span className="text-muted-foreground text-sm">
                      {includeVerification ? "Show confidence" : "Off"}
                    </span>
                  </div>
                </div>
              </div>

              <Button
                type="button"
                variant="secondary"
                onClick={handlePreviewSchema}
                disabled={
                  isLoading || isGeneratingSchema || !userRequirements.trim()
                }
                className="w-full"
              >
                {isGeneratingSchema ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating schema…
                  </>
                ) : (
                  <>
                    <FileCode2 className="mr-2 h-4 w-4" />
                    Preview schema
                  </>
                )}
              </Button>

              {generatedSchema && <SchemaPreview schema={generatedSchema} />}
            </CardContent>
          </Card>

          <Button
            onClick={handleSubmit}
            disabled={isLoading || files.length === 0 || !userRequirements.trim()}
            className="w-full"
            size="lg"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Extracting…
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Extract Data
              </>
            )}
          </Button>

          <HowItWorksCard description="One LLM call sees every PDF/image at once — no parse-then-extract round-trip.">
            <p>
              <strong>1. Upload one or more files.</strong> PDFs and images are
              all sent in the same request, so the model can cross-reference
              them (e.g. line items in a PO against quantities in a BOM).
            </p>
            <p>
              <strong>2. Describe what you want.</strong> Use a quick-start
              preset or write your own prompt — list the field names, types,
              and any constraints. A short, specific description gives a
              cleaner schema than a vague one.
            </p>
            <p>
              <strong>3. (Optional) Preview the schema.</strong> Click{" "}
              <em>Preview schema</em> to see the exact Pydantic class that will
              be returned. If the fields look wrong for your document, edit the
              prompt and regenerate — no LLM document call is made yet.
            </p>
            <p>
              <strong>4. Pick a provider.</strong> OpenAI/Azure works out of
              the box. Claude (Anthropic Foundry) and Google (Vertex AI) need
              their respective credentials configured.
            </p>
            <p>
              <strong>5. Optional verification.</strong> When enabled, every
              scalar field carries a confidence score and a short reason — useful
              for QA and human-in-the-loop workflows.
            </p>
          </HowItWorksCard>
        </div>

        {/* Results */}
        <div className="space-y-4">
          {isLoading && (
            <LoadingCard
              message="Calling vision model…"
              subMessage="Multi-doc extractions take a bit longer than a regular text pass"
            />
          )}

          {result && !isLoading && (
            <ResultCard
              title="Extracted Data"
              description={`Processed ${result.documents_processed} document(s) · ${result.duration_s.toFixed(2)}s · ${result.model}`}
              copyContent={JSON.stringify(result.data, null, 2)}
              feedbackSlot={<FeedbackButton demoType="vision-extractor" />}
              delay={0}
            >
              {result.usage && <UsageStats usage={result.usage} />}

              {Object.keys(result.data).length > 0 ? (
                <div className="divide-y rounded-md border">
                  {Object.entries(result.data).map(([key, value]) => (
                    <ExtractedFieldRow
                      key={key}
                      fieldKey={key}
                      value={value}
                      verification={verificationMap?.[key]}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground">No data extracted</p>
              )}
            </ResultCard>
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              icon={ScanEye}
              title="No extraction yet"
              description="Upload one or more files, describe what to extract, and click Extract Data."
              feedbackSlot={<FeedbackButton demoType="vision-extractor" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
