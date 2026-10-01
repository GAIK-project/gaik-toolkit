"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { FieldsTable } from "@/components/demo/schema-fields-table";
import type { SchemaField } from "@/components/demo/schema-fields-table";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FeedbackButton } from "@/components/feedback";
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
import { useModelSettings } from "@/lib/model-settings-store";
import { cn } from "@/lib/utils";
import {
  Database,
  FileText,
  ListChecks,
  Loader2,
  Plus,
  ScanText,
  Sparkles,
  Table2,
  Trash2,
  Upload,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  ACCEPTED_FILES,
  DEFAULT_PARSER,
  EXAMPLES,
  PARSERS,
  type ExtractorExample,
  type ParserType,
} from "./extractor-data";
import { ResultView } from "./result-view";

interface Field {
  name: string;
  description: string;
}

interface ExtractResult {
  results: Record<string, unknown>[];
  document_count: number;
}

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
  /** Newer servers: every field with its plain type, rule and nested records. */
  field_table?: SchemaField[];
}

type Phase = "schema" | "extracting" | null;

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Add the document",
    text: "Upload a PDF, Word file or image, paste text, or start from a ready-made document.",
  },
  {
    icon: ScanText,
    title: "Choose how it is read",
    text: "For an uploaded file, pick the parser that reads it. Auto-detect chooses by file type.",
  },
  {
    icon: ListChecks,
    title: "Say what to extract",
    text: "Describe it in words and generate the schema, or list the fields yourself.",
  },
  {
    icon: Table2,
    title: "Review the result",
    text: "Every field is shown, also those with no value. Copy or download the JSON.",
  },
];
const GUIDE_NOTES = [
  "Auto-detect reads a PDF with PyMuPDF, a Word file with DOCX and an image with Vision. A scanned PDF has no text layer: choose Vision, Vision+, Multimodal or the HH Parser.",
  "Nothing is saved. A generated schema lives for this session only.",
];

const STRUCTURE_TEXT: Record<string, string> = {
  flat: "One record: one set of fields for each document.",
  nested_list:
    "A list of records: the document holds several records of one kind.",
  parent_with_nested_list:
    "A header with a list inside: document fields plus repeated rows.",
};

const DEFAULT_FIELDS: Field[] = [
  { name: "company_name", description: "Name of the company or organization" },
  { name: "total_amount", description: "Total amount or price" },
  { name: "date", description: "Date of the document" },
];

const DEFAULT_TASK = EXAMPLES[0].task;

export default function ExtractorPage() {
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [documentText, setDocumentText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [parserType, setParserType] = useState<ParserType>(DEFAULT_PARSER);
  const [isParsing, setIsParsing] = useState(false);

  const [mode, setMode] = useState<"plain-language" | "fields">(
    "plain-language",
  );
  const [task, setTask] = useState(DEFAULT_TASK);
  const [userRequirements, setUserRequirements] = useState(
    "Extract key information from this document",
  );
  const [fields, setFields] = useState<Field[]>(DEFAULT_FIELDS);
  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldDesc, setNewFieldDesc] = useState("");
  const [schema, setSchema] = useState<
    (GeneratedSchema & { task: string }) | null
  >(null);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);

  const [exampleId, setExampleId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [phase, setPhase] = useState<Phase>(null);
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const ownModel = useModelSettings();

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  const schemaCurrent = schema !== null && schema.task === task.trim();
  const busy = isLoading || isParsing || isGeneratingSchema;
  const hasInput =
    inputMode === "text" ? documentText.trim().length > 0 : Boolean(file);
  const parser = PARSERS.find((p) => p.id === parserType) ?? PARSERS[0];

  async function pickExample(example: ExtractorExample): Promise<void> {
    setExampleId(example.id);
    setMode("plain-language");
    setTask(example.task);
    setSchema(null);
    setResult(null);
    try {
      const response = await fetch(example.url);
      if (!response.ok) throw new Error("Could not load the example");
      const blob = await response.blob();
      setFile(
        new File([blob], example.fileName, {
          type: blob.type || "application/pdf",
        }),
      );
      setInputMode("file");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed");
    }
  }

  function handleAddField(): void {
    if (!newFieldName.trim() || !newFieldDesc.trim()) return;
    const fieldKey = newFieldName.trim().toLowerCase().replace(/\s+/g, "_");
    if (fields.some((f) => f.name === fieldKey)) {
      toast.error("Field already exists");
      return;
    }
    setFields([
      ...fields,
      { name: fieldKey, description: newFieldDesc.trim() },
    ]);
    setNewFieldName("");
    setNewFieldDesc("");
  }

  /** Reads the file with the chosen parser; null if it failed. */
  async function parseFile(): Promise<string | null> {
    if (!file) return null;
    setIsParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", parserType);
      const response = await apiFetch("/api/parse", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current?.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to parse document");
      }
      const data = await response.json();
      return String(data.text_content ?? "");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return null;
      if (error instanceof RateLimitError) return null;
      toast.error(
        error instanceof Error ? error.message : "Failed to parse file",
      );
      return null;
    } finally {
      setIsParsing(false);
    }
  }

  async function generateSchema(): Promise<
    (GeneratedSchema & { task: string }) | null
  > {
    if (!task.trim()) {
      toast.error("Please provide extraction requirements");
      return null;
    }
    setIsGeneratingSchema(true);
    try {
      const response = await apiFetch("/api/extract/generate-schema", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_requirements: task }),
        signal: abortControllerRef.current?.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate schema");
      }
      const data = (await response.json()) as GeneratedSchema;
      const next = { ...data, task: task.trim() };
      setSchema(next);
      posthog.capture("schema_generated", {
        structure_type: data.structure_type,
        fields_count: data.fields?.length || 0,
      });
      return next;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return null;
      if (error instanceof RateLimitError) return null;
      toast.error(
        error instanceof Error ? error.message : "Failed to generate schema",
      );
      return null;
    } finally {
      setIsGeneratingSchema(false);
    }
  }

  async function handleGenerateSchema(): Promise<void> {
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const next = await generateSchema();
    if (next) toast.success("Schema generated");
  }

  async function handleSubmit(): Promise<void> {
    if (busy) return;
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    if (mode === "fields") {
      if (!userRequirements.trim()) {
        toast.error("Please provide extraction requirements");
        return;
      }
      if (fields.length === 0) {
        toast.error("Please add at least one field to extract");
        return;
      }
    } else if (!task.trim()) {
      toast.error("Please provide extraction requirements");
      return;
    }

    // The text to extract from: pasted, or read from the file by the parser.
    let text = documentText;
    if (inputMode === "file") {
      if (!file) {
        toast.error("Please select a file first");
        return;
      }
      const readable = await parseFile();
      if (readable === null) return;
      text = readable;
    }
    if (!text.trim()) {
      toast.error(
        inputMode === "file"
          ? "The parser found no text. Try another parser."
          : "Please provide document text",
      );
      return;
    }

    setIsLoading(true);
    setResult(null);
    setSeconds(null);
    const started = performance.now();

    try {
      let response: Response;
      if (mode === "fields") {
        setPhase("extracting");
        response = await apiFetch("/api/extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            documents: [text],
            user_requirements: userRequirements,
            fields: Object.fromEntries(
              fields.map((field) => [field.name, field.description]),
            ),
          }),
          signal: abortControllerRef.current.signal,
        });
      } else {
        // The schema is generated first when there is none for this task. It is kept in
        // memory only: nothing is saved by this demo.
        let current = schemaCurrent ? schema : null;
        if (!current) {
          setPhase("schema");
          current = await generateSchema();
          if (!current) return;
        }
        setPhase("extracting");
        response = await apiFetch("/api/extract/plain-language", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            documents: [text],
            user_requirements: task,
            schema_id: current.schema_id,
          }),
          signal: abortControllerRef.current.signal,
        });
      }

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to extract data");
      }
      const data = (await response.json()) as ExtractResult;
      setResult(data);
      setSeconds((performance.now() - started) / 1000);
      posthog.capture("data_extracted", {
        input_mode: inputMode,
        extraction_mode: mode,
        parser: inputMode === "file" ? parserType : null,
        example: exampleId,
        results_count: data.results?.length || 0,
      });
      toast.success("Data extracted");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
      setPhase(null);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Database}
        title="Extractor"
        description="Automatically find and list important details from any document"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Extractor"
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
                <ExamplePreviewDialog
                  exampleUrl={example.url}
                  exampleName={example.fileName}
                  onUseExample={() => void pickExample(example)}
                  disabled={busy}
                  label="View document"
                  buttonSize="xs"
                />
              </div>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>1. The document</CardTitle>
              <CardDescription>
                Upload a file and choose how it is read, or paste the text.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs
                value={inputMode}
                onValueChange={(v) => setInputMode(v as "text" | "file")}
              >
                <TabsList className="mb-4 grid w-full grid-cols-2">
                  <TabsTrigger value="text">Paste text</TabsTrigger>
                  <TabsTrigger value="file">Upload file</TabsTrigger>
                </TabsList>
                <TabsContent value="text">
                  <Textarea
                    value={documentText}
                    onChange={(e) => {
                      setDocumentText(e.target.value);
                      setExampleId(null);
                    }}
                    placeholder="Paste your document text here..."
                    disabled={busy}
                    rows={10}
                  />
                </TabsContent>
                <TabsContent value="file" className="space-y-4">
                  <FileUpload
                    accept={ACCEPTED_FILES}
                    maxSize={20}
                    file={file}
                    onFileSelect={(next) => {
                      setFile(next);
                      setExampleId(null);
                    }}
                    onFileRemove={() => setFile(null)}
                    disabled={busy}
                  />

                  <div className="space-y-2">
                    <Label htmlFor="extractor-parser">Parser</Label>
                    <Select
                      value={parserType}
                      onValueChange={(value) =>
                        setParserType(value as ParserType)
                      }
                      disabled={busy}
                    >
                      <SelectTrigger id="extractor-parser">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PARSERS.map((option) => (
                          <SelectItem key={option.id} value={option.id}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-muted-foreground text-xs">
                      {parser.hint}
                    </p>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. What to extract</CardTitle>
              <CardDescription>
                Describe the data in words, or list the fields yourself.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs
                value={mode}
                onValueChange={(v) => setMode(v as "plain-language" | "fields")}
              >
                <TabsList className="mb-4 grid w-full grid-cols-2">
                  <TabsTrigger value="plain-language">
                    Plain language
                  </TabsTrigger>
                  <TabsTrigger value="fields">Fields</TabsTrigger>
                </TabsList>

                <TabsContent value="plain-language" className="space-y-3">
                  <Label htmlFor="plain-requirements">
                    Extraction requirements
                  </Label>
                  <Textarea
                    id="plain-requirements"
                    value={task}
                    onChange={(e) => {
                      setTask(e.target.value);
                      setExampleId(null);
                    }}
                    placeholder="Describe in natural language what data to extract and the structure..."
                    disabled={busy}
                    rows={8}
                  />
                  <Button
                    onClick={() => void handleGenerateSchema()}
                    disabled={busy || !task.trim()}
                    variant="secondary"
                    className="w-full"
                  >
                    {isGeneratingSchema ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Generating schema…
                      </>
                    ) : (
                      <>
                        <ListChecks className="mr-2 h-4 w-4" />
                        {schema
                          ? "Generate the schema again"
                          : "Generate schema"}
                      </>
                    )}
                  </Button>
                  <p className="text-muted-foreground text-xs">
                    The schema is generated when you extract, if there is none
                    for this task. It is not saved.
                  </p>
                </TabsContent>

                <TabsContent value="fields" className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="requirements">Requirements</Label>
                    <Textarea
                      id="requirements"
                      value={userRequirements}
                      onChange={(e) => setUserRequirements(e.target.value)}
                      placeholder="Describe what data to extract..."
                      disabled={busy}
                      rows={2}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Fields to extract</Label>
                    <div className="max-h-48 space-y-2 overflow-auto">
                      {fields.map((field) => (
                        <div
                          key={field.name}
                          className="flex items-center gap-2 rounded-md border p-2 text-sm"
                        >
                          <div className="min-w-0 flex-1">
                            <span className="font-mono font-medium">
                              {field.name}
                            </span>
                            <span className="text-muted-foreground ml-2">
                              - {field.description}
                            </span>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0"
                            aria-label={`Remove ${field.name}`}
                            onClick={() =>
                              setFields(
                                fields.filter((f) => f.name !== field.name),
                              )
                            }
                            disabled={busy}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                      <Input
                        value={newFieldName}
                        onChange={(e) => setNewFieldName(e.target.value)}
                        placeholder="Field name"
                        disabled={busy}
                        className="w-full sm:flex-1"
                      />
                      <Input
                        value={newFieldDesc}
                        onChange={(e) => setNewFieldDesc(e.target.value)}
                        placeholder="Description"
                        disabled={busy}
                        className="w-full sm:flex-1"
                      />
                      <Button
                        variant="secondary"
                        size="icon"
                        aria-label="Add field"
                        onClick={handleAddField}
                        disabled={
                          busy || !newFieldName.trim() || !newFieldDesc.trim()
                        }
                        className="self-end sm:self-auto"
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </TabsContent>
              </Tabs>

              <Button
                onClick={() => void handleSubmit()}
                disabled={
                  busy ||
                  !hasInput ||
                  (mode === "fields" && fields.length === 0) ||
                  (mode === "plain-language" && !task.trim())
                }
                className="w-full"
                size="lg"
              >
                {isLoading || isParsing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {isParsing
                  ? "Reading the document…"
                  : isLoading
                    ? phase === "schema"
                      ? "Generating schema…"
                      : "Extracting…"
                    : "Extract data"}
              </Button>
              <p className="text-muted-foreground text-center text-xs">
                Model:{" "}
                {ownModel
                  ? `your own (${ownModel.model})`
                  : "the server's model"}
              </p>
            </CardContent>
          </Card>
        </div>

        {mode === "plain-language" && schema && !isLoading && (
          <Card>
            <CardContent className="pt-6">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">
                    The extraction schema
                  </CardTitle>
                  <span className="font-mono text-xs">
                    {schema.schema_name}
                  </span>
                  <Badge variant="secondary" className="font-mono font-normal">
                    {schema.structure_type}
                  </Badge>
                  {!schemaCurrent && (
                    <Badge
                      variant="outline"
                      className="border-amber-500 text-amber-700"
                    >
                      The task changed: generate again
                    </Badge>
                  )}
                </div>
                {STRUCTURE_TEXT[schema.structure_type] && (
                  <p className="text-muted-foreground text-xs">
                    {STRUCTURE_TEXT[schema.structure_type]}
                  </p>
                )}
                <Tabs
                  defaultValue={
                    schema.field_table && schema.field_table.length > 0
                      ? "fields"
                      : "code"
                  }
                >
                  <TabsList>
                    {schema.field_table && schema.field_table.length > 0 && (
                      <TabsTrigger value="fields">Fields</TabsTrigger>
                    )}
                    <TabsTrigger value="code">Python code</TabsTrigger>
                  </TabsList>
                  {schema.field_table && schema.field_table.length > 0 && (
                    <TabsContent value="fields" className="pt-2">
                      <FieldsTable fields={schema.field_table} />
                    </TabsContent>
                  )}
                  <TabsContent value="code" className="pt-2">
                    <pre className="bg-muted/40 max-h-64 overflow-auto rounded p-3 text-xs">
                      <code>{schema.schema_code}</code>
                    </pre>
                  </TabsContent>
                </Tabs>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="space-y-6" aria-live="polite">
          {(isLoading || isParsing) && (
            <LoadingCard
              message={
                isParsing
                  ? "Reading the document…"
                  : phase === "schema"
                    ? "Designing the extraction schema…"
                    : "Extracting data…"
              }
              subMessage={
                isParsing
                  ? `With the ${parser.label.split(" (")[0]} parser`
                  : "This may take a few seconds"
              }
            />
          )}

          {result && !isLoading && !isParsing && (
            <ResultView
              results={result.results}
              documentCount={result.document_count}
              seconds={seconds}
            />
          )}

          {!result && !isLoading && !isParsing && (
            <EmptyStateCard
              icon={FileText}
              title="No extraction yet"
              description="Add a document and press Extract data. Every field of the result is shown here, also those with no value."
              feedbackSlot={<FeedbackButton demoType="extractor" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
