"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileTypeIcon } from "@/components/demo/file-type-icon";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import type { SchemaField } from "@/components/demo/schema-fields-table";
import { schemaTabs, SchemaTabsView } from "@/components/demo/schema-views";
import { TaskChangeNotice } from "@/components/demo/task-change-notice";
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
import { RunBlockedButton, useRunAccess } from "@/components/run-access";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn, formatFileSize } from "@/lib/utils";
import { openFileInNewTab } from "@/components/demo/file-upload";
import {
  Check,
  ExternalLink,
  FileCode2,
  Loader2,
  ScanEye,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { ResultView, type Verification } from "../extractor/result-view";
import {
  SourcesView,
  TraceSourcesSwitch,
  type SourcesResult,
} from "./sources-view";
import {
  ACCEPTED_EXTENSIONS,
  EXAMPLES,
  fileNameOf,
  MAX_FILE_MB,
  MAX_FILES,
  runHint,
  type VisionExample,
} from "./vision-data";

const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");

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
  sources?: SourcesResult | null;
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

/** The heading of one step of the form: its number, what to do, and whether it can be skipped. */
function StepTitle({
  n,
  optional = false,
  children,
}: {
  n: number;
  optional?: boolean;
  children: string;
}) {
  return (
    <CardTitle className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      <span
        aria-hidden
        className="bg-primary text-primary-foreground flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums"
      >
        {n}
      </span>
      <span>
        <span className="sr-only">Step {n}: </span>
        {children}
      </span>
      {optional && (
        <span className="text-muted-foreground text-sm font-normal">
          Optional
        </span>
      )}
    </CardTitle>
  );
}

interface FileListRowProps {
  file: File;
  disabled: boolean;
  onRemove: () => void;
}

function FileListRow({ file, disabled, onRemove }: FileListRowProps) {
  return (
    <div className="flex items-center gap-2 rounded-md border p-2">
      <FileTypeIcon name={file.name} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{file.name}</p>
        <p className="text-muted-foreground text-xs">
          {formatFileSize(file.size)}
        </p>
      </div>
      <button
        type="button"
        onClick={() => openFileInNewTab(file)}
        className="hover:bg-muted rounded-full p-1 transition-colors"
        aria-label={`Open ${file.name} in a new tab`}
        title="Open in a new tab"
      >
        <ExternalLink className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={onRemove}
        disabled={disabled}
        className="hover:bg-muted rounded-full p-1 transition-colors"
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
  const [includeSources, setIncludeSources] = useState(true);
  const [exampleId, setExampleId] = useState<string | null>(null);
  // The task of the example that was picked: editing the text does not change it.
  const [exampleTask, setExampleTask] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);
  const [generatedSchema, setGeneratedSchema] =
    useState<GeneratedSchema | null>(null);
  const [result, setResult] = useState<VisionExtractResult | null>(null);
  // The schema the result was extracted with: it stays with the result when the task changes.
  const [resultSchema, setResultSchema] = useState<GeneratedSchema | null>(
    null,
  );
  const [isDragging, setIsDragging] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const schemaCardRef = useRef<HTMLDivElement | null>(null);
  // Counts the schema previews, so each one brings the schema card into view.
  const [previewCount, setPreviewCount] = useState(0);

  const busy = isLoading || isLoadingExample || isGeneratingSchema;
  const schemaCurrent =
    generatedSchema !== null &&
    normalizeTask(generatedSchema.user_requirements) ===
      normalizeTask(userRequirements);
  // The text no longer matches the schema in hand (or, before any schema, the picked
  // example): a new schema is generated at the next run.
  // The text is exactly an example's task that has a committed schema (also after the
  // text was edited and put back).
  const readyMade = EXAMPLES.some(
    (e) =>
      e.readyMade && normalizeTask(e.task) === normalizeTask(userRequirements),
  );
  const taskChanged = generatedSchema
    ? !schemaCurrent
    : exampleTask !== null &&
      normalizeTask(userRequirements) !== normalizeTask(exampleTask);
  // A run generates no schema: one was previewed for this text, or the text is an
  // example's with a ready-made one.
  const schemaReady = schemaCurrent || (!generatedSchema && readyMade);
  const { blocked: runBlocked } = useRunAccess();
  const loadedExample = EXAMPLES.find((e) => e.id === exampleId) ?? null;
  const run = runHint({
    loadingExample: isLoadingExample,
    generatingSchema: isGeneratingSchema,
    extracting: isLoading,
    fileCount: files.length,
    hasTask: userRequirements.trim().length > 0,
    schemaReady,
  });

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
    if (next) {
      toast.success("Schema generated");
      setPreviewCount((count) => count + 1);
    }
  }

  useEffect(() => {
    if (previewCount === 0) return;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    schemaCardRef.current?.scrollIntoView({
      behavior: reduced ? "auto" : "smooth",
      block: "nearest",
    });
  }, [previewCount]);

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
      if (files.length + accepted.length >= MAX_FILES) {
        errors.push(`${file.name}: at most ${MAX_FILES} files per extraction`);
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
      setExampleTask(example.task);
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

      const send = (current: GeneratedSchema): Promise<Response> => {
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }
        formData.append("user_requirements", userRequirements);
        formData.append("schema_id", current.schema_id);
        appendVisionSettings(formData, settings, model);
        formData.append("include_sources", includeSources ? "true" : "false");
        return apiFetch("/api/extract-vision", {
          method: "POST",
          body: formData,
          signal: abortControllerRef.current?.signal,
        });
      };

      let response = await send(schema);
      // The server forgot the schema of the earlier run (it restarted, or made many
      // newer ones): make it again and retry once.
      if (
        (response.status === 410 || response.status === 409) &&
        schemaCurrent
      ) {
        const fresh = await generateSchema();
        if (!fresh) return;
        response = await send(fresh);
      }

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Vision extraction failed");
      }

      const data = (await response.json()) as VisionExtractResult;
      setResult(data);
      setResultSchema(schema);

      posthog.capture("vision_extracted", {
        provider: settings.provider,
        documents_processed: data.documents_processed,
        include_verification: includeVerification,
        include_sources: includeSources,
        total_tokens: data.usage?.total_tokens ?? 0,
        example: exampleId,
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={ScanEye}
        title="Vision Extractor"
        description="Turn PDFs and images into validated, structured data in a single model call"
        className="mb-6"
      />

      <div className="space-y-6">
        <section className="space-y-3" aria-labelledby="vx-examples">
          <div className="space-y-1">
            <h2 id="vx-examples" className="text-sm font-semibold">
              Start with an example
            </h2>
            <p className="text-muted-foreground text-sm">
              Using an example fills in steps 1 and 2 for you. For your own
              documents, start at step 1.
            </p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {EXAMPLES.map((example) => {
              const loaded = exampleId === example.id;
              return (
                <li
                  key={example.id}
                  className={cn(
                    "flex flex-col gap-1.5 rounded-xl border-2 p-3 transition-colors",
                    loaded ? "border-primary bg-primary/5" : "bg-card",
                  )}
                >
                  <h3 className="font-semibold">{example.title}</h3>
                  <p className="text-muted-foreground flex-1 text-sm">
                    {example.summary}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      aria-pressed={loaded}
                      aria-label={
                        loaded
                          ? `${example.title}: loaded in the form`
                          : `Use the example ${example.title}`
                      }
                      disabled={busy}
                      onClick={() => void pickExample(example)}
                      className={cn(
                        loaded &&
                          "border-primary text-primary hover:text-primary",
                      )}
                    >
                      {loaded && <Check aria-hidden />}
                      {loaded ? "Loaded in the form" : "Use this example"}
                    </Button>
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
                </li>
              );
            })}
          </ul>
        </section>

        <div className="grid items-start gap-6 lg:grid-cols-2 lg:grid-rows-[auto_1fr]">
          <Card className="lg:col-start-1 lg:row-start-1">
            <CardHeader>
              <StepTitle n={1}>Add the documents</StepTitle>
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
                      : "Drag and drop files, or click to choose"}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    Up to {MAX_FILES} files of {MAX_FILE_MB} MB each: PDF, PNG,
                    JPG, GIF, WEBP, TIFF or BMP
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
                  {loadedExample ? (
                    <p className="text-primary flex items-start gap-1.5 text-xs font-medium">
                      <Check className="mt-px size-3.5 shrink-0" aria-hidden />
                      Loaded from the example “{loadedExample.title}”
                    </p>
                  ) : (
                    <p className="text-xs font-medium">
                      {pluralize(files.length, "file")} selected
                    </p>
                  )}
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

              <p className="text-muted-foreground text-xs">
                One model call sees every file at once, so it can match values
                across documents, for example an invoice against its purchase
                order. Nothing you enter is saved.
              </p>
            </CardContent>
          </Card>

          <Card className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <CardHeader>
              <StepTitle n={2}>Say what to extract</StepTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-2">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <Label htmlFor="requirements">Extraction requirements</Label>
                  {loadedExample && (
                    <span className="text-primary flex items-center gap-1.5 text-xs font-medium">
                      <Check className="size-3.5 shrink-0" aria-hidden />
                      Filled in from the example
                    </span>
                  )}
                </div>
                <Textarea
                  id="requirements"
                  value={userRequirements}
                  onChange={(e) => handleRequirementsChange(e.target.value)}
                  placeholder="e.g. Extract company name, total amount, date, and a list of line items (description, quantity, unit price) from this invoice."
                  disabled={busy}
                  rows={8}
                  className="max-h-80"
                />
                {taskChanged && userRequirements.trim() ? (
                  <TaskChangeNotice />
                ) : (
                  <p className="text-muted-foreground text-xs">
                    {schemaReady
                      ? "A schema for this text is ready. If you edit the text, a new schema is generated when you extract."
                      : "Name the fields and their types. A schema is generated from this text when you extract."}
                  </p>
                )}
              </div>

              {!runBlocked &&
                !(
                  schemaCurrent && generatedSchema?.schema_source === "example"
                ) && (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void handleGenerateSchema()}
                      disabled={busy || !userRequirements.trim()}
                    >
                      {isGeneratingSchema && !isLoading ? (
                        <Loader2 className="animate-spin" aria-hidden />
                      ) : (
                        <FileCode2 aria-hidden />
                      )}
                      {isGeneratingSchema && !isLoading
                        ? "Generating the schema…"
                        : schemaCurrent
                          ? "Generate the schema again"
                          : "Preview the schema"}
                    </Button>
                    <span className="text-muted-foreground text-xs">
                      {schemaCurrent
                        ? "Makes a new schema from the same text."
                        : "Optional: check the fields before you extract."}
                    </span>
                  </div>
                )}
            </CardContent>
          </Card>

          <Card className="lg:col-start-1 lg:row-start-2">
            <CardHeader>
              <StepTitle n={3} optional>
                Choose the model and options
              </StepTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <TraceSourcesSwitch
                checked={includeSources}
                onCheckedChange={setIncludeSources}
                disabled={busy}
              />
              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="settings" className="rounded-lg border">
                  <AccordionTrigger className="px-3 text-sm">
                    Model, reasoning effort and other options
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
            </CardContent>
          </Card>
        </div>

        {generatedSchema &&
          !isLoading &&
          (!result ||
            generatedSchema.schema_id !== resultSchema?.schema_id) && (
            <Card ref={schemaCardRef} className="scroll-mt-24">
              <CardContent className="space-y-3 pt-6">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">
                    The extraction schema
                  </CardTitle>
                  {generatedSchema.schema_source === "example" && (
                    <Badge variant="outline" className="font-normal">
                      built-in example schema
                    </Badge>
                  )}
                </div>
                {!schemaCurrent && (
                  <p className="text-muted-foreground text-sm">
                    Made from an earlier version of the text in step 2. A new
                    schema is generated when you extract.
                  </p>
                )}
                <SchemaTabsView
                  tabs={schemaTabs(
                    generatedSchema,
                    STRUCTURE_TEXT[generatedSchema.structure_type],
                  )}
                />
              </CardContent>
            </Card>
          )}

        <Card>
          <CardHeader>
            <StepTitle n={4}>Extract</StepTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
              {runBlocked ? (
                <div className="shrink-0">
                  <RunBlockedButton />
                </div>
              ) : (
                <Button
                  onClick={() => void handleSubmit()}
                  disabled={!run.ready}
                  size="lg"
                  className="w-full sm:w-auto sm:min-w-44"
                >
                  {isLoading ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <Sparkles aria-hidden />
                  )}
                  {isLoading
                    ? isGeneratingSchema
                      ? "Generating schema…"
                      : "Extracting…"
                    : "Extract data"}
                </Button>
              )}
              <p
                role="status"
                className={cn(
                  "text-sm",
                  run.ready || runBlocked
                    ? "text-muted-foreground"
                    : "text-foreground",
                )}
              >
                {runBlocked
                  ? "A run generates a schema from your text when there is none, then reads every file in one model call."
                  : run.text}
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6" aria-live="polite">
          {isLoading && (
            <LoadingCard
              message={
                isGeneratingSchema
                  ? "Designing the extraction schema…"
                  : "Calling vision model…"
              }
            />
          )}

          {result && !isLoading && (
            <ResultView
              results={[result.data]}
              documentCount={result.documents_processed}
              seconds={result.duration_s}
              detail={result.model}
              verification={includeVerification ? result.verification : null}
              extraTabs={[
                ...(result.sources
                  ? [
                      {
                        value: "sources",
                        label: "Sources",
                        content: <SourcesView result={result.sources} />,
                      },
                    ]
                  : []),
                ...(resultSchema
                  ? schemaTabs(
                      resultSchema,
                      STRUCTURE_TEXT[resultSchema.structure_type],
                    )
                  : []),
              ]}
            >
              {result.usage && <UsageStats usage={result.usage} />}
            </ResultView>
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              icon={ScanEye}
              title="No extraction yet"
              description="Every field of the result appears here, with the place in the document it was read from."
              feedbackSlot={<FeedbackButton demoType="vision-extractor" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
