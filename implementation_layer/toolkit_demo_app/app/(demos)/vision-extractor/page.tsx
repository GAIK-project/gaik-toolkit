"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { FieldsTable } from "@/components/demo/schema-fields-table";
import type { SchemaField } from "@/components/demo/schema-fields-table";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import {
  appendVisionSettings,
  DEFAULT_VISION_SETTINGS,
  resolveVisionModel,
  UsageStats,
  type VisionUsage,
  VisionSettingsFields,
  useVisionModels,
} from "@/components/demo/vision-settings";
import { FeedbackButton } from "@/components/feedback";
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
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn, formatFileSize } from "@/lib/utils";
import {
  CheckCircle,
  File as FileIcon,
  FileCode2,
  ListChecks,
  Loader2,
  ScanEye,
  ShieldCheck,
  Sparkles,
  Table2,
  Upload,
  X,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { ResultView, type Verification } from "../extractor/result-view";
import {
  ACCEPTED_EXTENSIONS,
  EXAMPLES,
  fileNameOf,
  MAX_FILE_MB,
  type VisionExample,
} from "./vision-data";

const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Add the documents",
    text: "Upload PDFs and images, one or several. Or use one of the ready-made documents.",
  },
  {
    icon: ListChecks,
    title: "Say what to extract",
    text: "Describe the fields in words. The schema is generated for you to check.",
  },
  {
    icon: ShieldCheck,
    title: "Choose the model",
    text: "Pick the model and options. Turn on verification to get a confidence score for each field.",
  },
  {
    icon: Table2,
    title: "Review the result",
    text: "Fields, lists as tables, and the confidence of each value. Copy or download the JSON.",
  },
];
const GUIDE_NOTES = [
  "One model call sees every file at once, so it can match values across documents, for example an invoice against its purchase order. There is no parsing step before it.",
  "Nothing is saved. A generated schema lives for this session only.",
];

const STRUCTURE_TEXT: Record<string, string> = {
  flat: "One record: one set of fields for all the documents.",
  nested_list:
    "A list of records: the documents hold several records of one kind.",
  parent_with_nested_list:
    "A header with a list inside: document fields plus repeated rows.",
};

interface GeneratedSchema {
  schema_code: string;
  schema_name: string;
  structure_type: string;
  schema_id: string;
  schema_source: "example" | "temporary";
  user_requirements: string;
  fields: Array<{
    name: string;
    type: string;
    description: string;
    required: boolean;
  }>;
  /** Newer servers: every field with its plain type, rule and nested records. */
  field_table?: SchemaField[];
  /** The requirements the schema was built from, as JSON. */
  requirements_json?: string;
}

interface VisionExtractResult {
  data: Record<string, unknown>;
  verification: Verification | null;
  model: string;
  documents_processed: number;
  duration_s: number;
  usage: VisionUsage | null;
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

function pluralize(
  count: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

const normalizeTask = (value: string): string =>
  value.replace(/\r\n?/g, "\n").trim();

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
        <p className="text-muted-foreground text-xs">
          {formatFileSize(file.size)}
        </p>
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

export default function VisionExtractorPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [userRequirements, setUserRequirements] = useState("");
  const [settings, setSettings] = useState(DEFAULT_VISION_SETTINGS);
  const catalogue = useVisionModels();
  const model = resolveVisionModel(settings, catalogue);
  const { includeVerification } = settings;
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);
  const [generatedSchema, setGeneratedSchema] =
    useState<GeneratedSchema | null>(null);
  const [result, setResult] = useState<VisionExtractResult | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const busy = isLoading || isLoadingExample || isGeneratingSchema;
  const schemaCurrent =
    generatedSchema !== null &&
    normalizeTask(generatedSchema.user_requirements) ===
      normalizeTask(userRequirements);

  function handleRequirementsChange(value: string): void {
    setUserRequirements(value);
    setExampleId(null);
  }

  /** Generates a schema for the task now in the box; null if that failed. */
  async function generateSchema(): Promise<GeneratedSchema | null> {
    if (!userRequirements.trim()) {
      toast.error("Please describe what to extract first");
      return null;
    }
    setIsGeneratingSchema(true);
    try {
      const response = await apiFetch("/api/extract-vision/generate-schema", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_requirements: userRequirements }),
        signal: abortControllerRef.current?.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate schema");
      }
      const data = (await response.json()) as GeneratedSchema;
      setGeneratedSchema(data);
      return data;
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return null;
      if (err instanceof RateLimitError) return null;
      toast.error(
        err instanceof Error ? err.message : "Failed to generate schema",
      );
      return null;
    } finally {
      setIsGeneratingSchema(false);
    }
  }

  async function handleGenerateSchema(): Promise<void> {
    if (busy) return;
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const next = await generateSchema();
    if (next) toast.success("Schema generated");
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
      setExampleId(null);
    }
  }

  function removeFile(index: number): void {
    setFiles(files.filter((_, i) => i !== index));
    setExampleId(null);
  }

  async function pickExample(example: VisionExample): Promise<void> {
    if (busy) return;
    setIsLoadingExample(true);
    try {
      const fetched = await Promise.all(
        example.files.map(async ({ url }) => {
          const res = await fetch(url);
          if (!res.ok) throw new Error(`Failed to load ${fileNameOf(url)}`);
          const blob = await res.blob();
          return new File([blob], fileNameOf(url), {
            type: blob.type || "application/octet-stream",
          });
        }),
      );
      setFiles(fetched);
      setUserRequirements(example.task);
      setGeneratedSchema(null);
      setExampleId(example.id);
      setResult(null);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load example",
      );
    } finally {
      setIsLoadingExample(false);
    }
  }

  // The first example is loaded and selected when the page opens.
  useEffect(() => {
    void pickExample(EXAMPLES[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(): Promise<void> {
    if (busy) return;
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
      // The schema is generated first when there is none for this task. It is
      // kept in memory only: nothing is saved by this demo.
      const schema = schemaCurrent ? generatedSchema : await generateSchema();
      if (!schema) return;

      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      formData.append("user_requirements", userRequirements);
      formData.append("schema_id", schema.schema_id);
      appendVisionSettings(formData, settings, model);

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
        provider: settings.provider,
        documents_processed: data.documents_processed,
        include_verification: includeVerification,
        total_tokens: data.usage?.total_tokens ?? 0,
        example: exampleId,
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

  const hasTable = (generatedSchema?.field_table?.length ?? 0) > 0;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={ScanEye}
        title="Vision Extractor"
        description="Turn PDFs and images into validated, structured data in a single model call"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Vision Extractor"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">
            Start from a ready-made document
          </h2>
          <div
            role="radiogroup"
            aria-label="Ready-made documents"
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
          >
            {EXAMPLES.map((example) => (
              <div
                key={example.id}
                className={cn(
                  "flex flex-col gap-1.5 rounded-xl border-2 p-3 transition-all",
                  exampleId === example.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={exampleId === example.id}
                  disabled={busy}
                  onClick={() => void pickExample(example)}
                  className="flex flex-1 flex-col gap-1.5 text-left"
                >
                  <span className="font-semibold">{example.title}</span>
                  <span className="text-muted-foreground text-sm">
                    {example.summary}
                  </span>
                  <span>
                    <Badge variant="outline" className="font-normal">
                      {example.shape}
                    </Badge>
                  </span>
                </button>
                <div className="flex flex-wrap justify-center gap-1">
                  {example.files.map((file) => (
                    <ExamplePreviewDialog
                      key={file.url}
                      exampleUrl={file.url}
                      exampleName={fileNameOf(file.url)}
                      onUseExample={() => void pickExample(example)}
                      disabled={busy}
                      label={
                        example.files.length === 1
                          ? "View document"
                          : `View ${file.label}`
                      }
                      buttonSize="xs"
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>1. The documents</CardTitle>
              <CardDescription>
                PDFs or images, read together so the model can match across
                files.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <label
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!busy && e.dataTransfer.files.length > 0) {
                    addFiles(e.dataTransfer.files);
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (!busy) setIsDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                }}
                className={`flex min-h-[140px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 transition-all ${
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
                } ${busy ? "cursor-not-allowed opacity-50" : ""}`}
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
                    PDF, PNG, JPG, GIF, WEBP, TIFF, BMP — up to {MAX_FILE_MB}MB
                    each
                  </p>
                </div>
                <input
                  type="file"
                  accept={ACCEPT_ATTR}
                  multiple
                  disabled={busy}
                  onChange={(e) => {
                    if (e.target.files) {
                      addFiles(e.target.files);
                      e.target.value = "";
                    }
                  }}
                  className="sr-only"
                />
              </label>

              {isLoadingExample && (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading the example…
                </p>
              )}

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
                        disabled={busy}
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
              <CardTitle>2. What to extract</CardTitle>
              <CardDescription>
                Describe the fields in plain language. The schema is generated
                when you extract, or earlier with the button below.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="requirements">Extraction requirements</Label>
                <Textarea
                  id="requirements"
                  value={userRequirements}
                  onChange={(e) => handleRequirementsChange(e.target.value)}
                  placeholder="e.g. Extract company name, total amount, date, and a list of line items (description, quantity, unit price) from this invoice."
                  disabled={busy}
                  rows={8}
                />
                <p className="text-muted-foreground text-xs">
                  Be specific about field names and types. The clearer your
                  description, the better the generated schema.
                </p>
              </div>

              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="settings" className="rounded-lg border">
                  <AccordionTrigger className="px-3 text-sm">
                    Model and options
                  </AccordionTrigger>
                  <AccordionContent className="px-3">
                    <VisionSettingsFields
                      settings={settings}
                      catalogue={catalogue}
                      disabled={busy}
                      onChange={setSettings}
                    />
                  </AccordionContent>
                </AccordionItem>
              </Accordion>

              <Button
                type="button"
                variant="secondary"
                onClick={() => void handleGenerateSchema()}
                disabled={busy || !userRequirements.trim()}
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
                    {generatedSchema
                      ? "Generate the schema again"
                      : "Generate schema"}
                  </>
                )}
              </Button>

              <Button
                onClick={() => void handleSubmit()}
                disabled={
                  busy || files.length === 0 || !userRequirements.trim()
                }
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {isGeneratingSchema ? "Generating schema…" : "Extracting…"}
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Extract data
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        {generatedSchema && !isLoading && (
          <Card>
            <CardContent className="space-y-3 pt-6">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-base">
                  The extraction schema
                </CardTitle>
                <span className="font-mono text-xs">
                  {generatedSchema.schema_name}
                </span>
                <Badge variant="secondary" className="font-mono font-normal">
                  {generatedSchema.structure_type}
                </Badge>
                {generatedSchema.schema_source === "example" && (
                  <Badge variant="outline" className="font-normal">
                    built-in example schema
                  </Badge>
                )}
                {!schemaCurrent && (
                  <Badge
                    variant="outline"
                    className="border-amber-500 text-amber-700"
                  >
                    The task changed: generate again
                  </Badge>
                )}
              </div>
              {STRUCTURE_TEXT[generatedSchema.structure_type] && (
                <p className="text-muted-foreground text-xs">
                  {STRUCTURE_TEXT[generatedSchema.structure_type]}
                </p>
              )}
              <Tabs defaultValue={hasTable ? "fields" : "code"}>
                <TabsList>
                  {hasTable && <TabsTrigger value="fields">Fields</TabsTrigger>}
                  <TabsTrigger value="code">Python code</TabsTrigger>
                  {generatedSchema.requirements_json && (
                    <TabsTrigger value="requirements">
                      requirements.json
                    </TabsTrigger>
                  )}
                </TabsList>
                {hasTable && (
                  <TabsContent value="fields" className="pt-2">
                    <FieldsTable fields={generatedSchema.field_table ?? []} />
                  </TabsContent>
                )}
                <TabsContent value="code" className="pt-2">
                  <pre className="bg-muted/40 max-h-72 overflow-auto rounded p-3 text-xs">
                    <code>{generatedSchema.schema_code}</code>
                  </pre>
                </TabsContent>
                {generatedSchema.requirements_json && (
                  <TabsContent value="requirements" className="pt-2">
                    <pre className="bg-muted/40 max-h-72 overflow-auto rounded p-3 text-xs">
                      <code>{generatedSchema.requirements_json}</code>
                    </pre>
                  </TabsContent>
                )}
              </Tabs>
            </CardContent>
          </Card>
        )}

        <div className="space-y-6" aria-live="polite">
          {isLoading && (
            <LoadingCard
              message={
                isGeneratingSchema
                  ? "Designing the extraction schema…"
                  : "Calling vision model…"
              }
              subMessage="Multi-document extractions take a bit longer than a regular text pass"
            />
          )}

          {result && !isLoading && (
            <ResultView
              results={[result.data]}
              documentCount={result.documents_processed}
              seconds={result.duration_s}
              detail={result.model}
              verification={includeVerification ? result.verification : null}
            >
              {result.usage && <UsageStats usage={result.usage} />}
            </ResultView>
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              icon={ScanEye}
              title="No extraction yet"
              description="Add documents, describe what to extract, and click Extract data. Every field of the result is shown here, also those with no value."
              feedbackSlot={<FeedbackButton demoType="vision-extractor" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
